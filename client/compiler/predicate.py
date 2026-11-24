#!/usr/bin/env python3
"""Transpile expression predicates from the pipeline config into C++ and build them as shared libraries.

Exposes ExprTranspiler (expression to C++ source) and PredicateCompiler (source to .so).
"""

from __future__ import annotations

import ast
import re
import subprocess
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config_schema import ExprPredicateConfig

_ALLOWED_BODY_NODES = frozenset({
    ast.Expression,
    ast.Constant,
    ast.Name,
    ast.BoolOp, ast.And, ast.Or,
    ast.UnaryOp, ast.Not, ast.USub, ast.UAdd,
    ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div,
    ast.Compare,
    ast.Gt, ast.Lt, ast.GtE, ast.LtE, ast.Eq, ast.NotEq,
})

_CPP_HELPERS = textwrap.dedent("""\
    namespace {

    inline int ax_num_dets(const Ax::MetaMap &meta, const char *key)
    {
        auto it = meta.find(key);
        if (it == meta.end()) return 0;
        auto *b = dynamic_cast<const AxMetaBbox *>(it->second.get());
        return b ? static_cast<int>(b->num_elements()) : 0;
    }

    inline float ax_max_score(const Ax::MetaMap &meta, const char *key)
    {
        auto it = meta.find(key);
        if (it == meta.end()) return 0.f;
        auto *b = dynamic_cast<const AxMetaBbox *>(it->second.get());
        if (!b || b->num_elements() == 0) return 0.f;
        float m = 0.f;
        for (size_t i = 0; i < b->num_elements(); ++i)
            m = std::max(m, b->score(static_cast<int>(i)));
        return m;
    }

    inline bool ax_meta_exists(const Ax::MetaMap &meta, const char *key)
    {
        return meta.find(key) != meta.end();
    }

    inline bool ax_has_class(const Ax::MetaMap &meta, const char *key,
                              int class_id)
    {
        auto it = meta.find(key);
        if (it == meta.end()) return false;
        auto *b = dynamic_cast<const AxMetaBbox *>(it->second.get());
        if (!b) return false;
        for (size_t i = 0; i < b->num_elements(); ++i)
            if (b->class_id(static_cast<int>(i)) == class_id) return true;
        return false;
    }

    inline bool ax_kpts_all_confident(const Ax::MetaMap &meta, const char *key,
                                       float min_conf, int i0, int i1, int i2)
    {
        auto it = meta.find(key);
        if (it == meta.end()) return false;
        auto *kd = dynamic_cast<const AxMetaKptsDetection *>(it->second.get());
        if (!kd) return false;
        const auto kshape = kd->get_kpts_shape();
        const size_t n_kpts = kshape.empty() ? 17u : static_cast<size_t>(kshape[0]);
        if (n_kpts == 0) return false;
        try {
            const auto kpts = kd->get_kpts_xyv(0, n_kpts);
            for (int idx : {i0, i1, i2}) {
                if (idx < 0 || static_cast<size_t>(idx) >= kpts.size()) return false;
                if (kpts[idx].visibility <= min_conf) return false;
            }
            return true;
        } catch (const std::out_of_range &) {
            return false;
        }
    }

    } // anonymous namespace
""")

_HELPER_RE = re.compile(
    r'^(num_detections|max_score|meta_exists|has_class|kpts_all_confident)\s*\((.+)\)$'
)


class ExprTranspiler:
    """Translates an 'expr' predicate (named inputs plus a Python boolean expression) into C++ source.

    Inputs map variable names to helper calls such as "num_detections('key')". The body is a
    restricted Python expression over those variables (comparisons, and/or/not, + - * /).
    generate_cpp() returns a translation unit defining an Ax::Predicate plugin.
    """

    def __init__(self, name: str, inputs: dict[str, str], body: str) -> None:
        """Store the predicate definition.

        Args:
            name (str): Predicate name; sanitised into the generated C++ class name.
            inputs (dict[str, str]): Variable name to helper-call string, e.g. {'n': "num_detections('det')"}.
            body (str): Python expression over the input variables.
        """
        self._name = name
        self._inputs = inputs
        self._body = body

    def _parse_input(self, var: str, call: str) -> tuple[str, str]:
        """Translate one input helper call into a C++ type and initialiser expression.

        Supported helpers: num_detections, max_score, meta_exists, has_class, kpts_all_confident.

        Args:
            var (str): Input variable name, used in error messages.
            call (str): Helper call text, e.g. "has_class('det', 0)".

        Returns:
            tuple[str, str]: C++ type name ('int', 'float' or 'bool') and the C++ right-hand side.

        Raises:
            ValueError: If the helper is unsupported, has the wrong argument count, or has a non-numeric argument where one is required.
        """
        call = call.strip()
        m = _HELPER_RE.match(call)
        if not m:
            raise ValueError(
                f"Input '{var}': unsupported helper {call!r}. "
                "Supported: num_detections('key'), max_score('key'), "
                "meta_exists('key'), has_class('key', class_id), "
                "kpts_all_confident('key', min_conf, i0, i1, i2)"
            )
        fn, args_str = m.group(1), m.group(2)
        args = [a.strip().strip("'\"") for a in args_str.split(",") if a.strip()]

        if fn == "num_detections":
            if len(args) != 1:
                raise ValueError(f"num_detections requires exactly 1 argument, got {args}")
            return "int", f'ax_num_dets(meta, "{args[0]}")'
        if fn == "max_score":
            if len(args) != 1:
                raise ValueError(f"max_score requires exactly 1 argument, got {args}")
            return "float", f'ax_max_score(meta, "{args[0]}")'
        if fn == "meta_exists":
            if len(args) != 1:
                raise ValueError(f"meta_exists requires exactly 1 argument, got {args}")
            return "bool", f'ax_meta_exists(meta, "{args[0]}")'
        if fn == "has_class":
            if len(args) != 2:
                raise ValueError(f"has_class requires exactly 2 arguments, got {args}")
            return "bool", f'ax_has_class(meta, "{args[0]}", {int(args[1])})'
        if fn == "kpts_all_confident":
            if len(args) != 5:
                raise ValueError(
                    f"kpts_all_confident requires exactly 5 arguments "
                    f"(key, min_confidence, i0, i1, i2), got {args}"
                )
            key, min_conf, i0, i1, i2 = args
            return "bool", (
                f'ax_kpts_all_confident(meta, "{key}", {float(min_conf)}f, '
                f'{int(i0)}, {int(i1)}, {int(i2)})'
            )
        raise AssertionError(f"Unhandled fn: {fn}")

    def _to_cpp(self, node: ast.AST) -> str:
        """Render a Python AST node of the expression body as a fully parenthesised C++ expression.

        Raises:
            ValueError: For disallowed node types, undeclared names, unsupported operators or chained comparisons.
        """
        if type(node) not in _ALLOWED_BODY_NODES:
            raise ValueError(
                f"Forbidden construct in expr body: {type(node).__name__}. "
                "Only comparisons, boolean logic, and arithmetic are allowed."
            )
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return "true" if node.value else "false"
            if isinstance(node.value, float):
                return f"{node.value}f"
            return str(node.value)
        if isinstance(node, ast.Name):
            if node.id not in self._inputs:
                raise ValueError(
                    f"Unknown name '{node.id}' in body. "
                    f"Declared inputs: {list(self._inputs)}"
                )
            return node.id
        if isinstance(node, ast.BoolOp):
            sep = " && " if isinstance(node.op, ast.And) else " || "
            return "(" + sep.join(self._to_cpp(v) for v in node.values) + ")"
        if isinstance(node, ast.UnaryOp):
            if isinstance(node.op, ast.Not):
                return f"(!{self._to_cpp(node.operand)})"
            if isinstance(node.op, ast.USub):
                return f"(-{self._to_cpp(node.operand)})"
            if isinstance(node.op, ast.UAdd):
                return f"(+{self._to_cpp(node.operand)})"
            raise ValueError(f"Unsupported unary op: {type(node.op).__name__}")
        if isinstance(node, ast.BinOp):
            _OPS = {
                ast.Add: "+", ast.Sub: "-",
                ast.Mult: "*", ast.Div: "/",
            }
            op = _OPS.get(type(node.op))
            if op is None:
                raise ValueError(f"Unsupported binary op: {type(node.op).__name__}")
            return f"({self._to_cpp(node.left)} {op} {self._to_cpp(node.right)})"
        if isinstance(node, ast.Compare):
            if len(node.ops) != 1 or len(node.comparators) != 1:
                raise ValueError(
                    "Only single comparisons are supported in body "
                    "(e.g. 'n > 5', not chained 'a < n < b')"
                )
            _CMP = {
                ast.Gt: ">", ast.Lt: "<",
                ast.GtE: ">=", ast.LtE: "<=",
                ast.Eq: "==", ast.NotEq: "!=",
            }
            op = _CMP.get(type(node.ops[0]))
            if op is None:
                raise ValueError(f"Unsupported comparison: {type(node.ops[0]).__name__}")
            return (
                f"({self._to_cpp(node.left)} {op} "
                f"{self._to_cpp(node.comparators[0])})"
            )
        raise AssertionError(f"Unhandled node: {type(node).__name__}")

    def generate_cpp(self) -> str:
        """Generate the C++ source of the predicate plugin.

        The output declares each input as a const local read from the frame's meta map, evaluates
        the translated body, and exports ax_create_predicate / ax_destroy_predicate.

        Returns:
            str: Complete C++ translation unit.

        Raises:
            ValueError: If the body has a syntax error, uses a forbidden construct, or an input is invalid.
        """
        try:
            tree = ast.parse(self._body, mode="eval")
        except SyntaxError as exc:
            raise ValueError(
                f"Syntax error in expr body {self._body!r}: {exc}"
            ) from exc

        for node in ast.walk(tree):
            if isinstance(node, (ast.Load, ast.Store, ast.Del)):
                continue
            if type(node) not in _ALLOWED_BODY_NODES:
                raise ValueError(
                    f"Forbidden construct in expr body: {type(node).__name__}. "
                    "Only comparisons, boolean logic, and arithmetic are allowed."
                )

        cpp_body = self._to_cpp(tree.body)

        decls = []
        for var, call in self._inputs.items():
            cpp_type, cpp_rhs = self._parse_input(var, call)
            decls.append(f"        const {cpp_type} {var} = {cpp_rhs};")
        decl_block = "\n".join(decls)

        safe = "".join(c if c.isalnum() or c == "_" else "_" for c in self._name)

        return textwrap.dedent(f"""\
            // Auto-generated by ExprTranspiler — DO NOT EDIT
            #include <algorithm>
            #include <string>
            #include "pipeline/predicate.h"
            #include "pipeline/frame.h"
            #include "AxMetaBBox.hpp"
            #include "AxMetaKptsDetection.hpp"

            {_CPP_HELPERS}
            struct GeneratedPredicate_{safe} : Ax::Predicate {{
                bool eval(const Ax::Frame &frame) const override
                {{
                    const Ax::MetaMap &meta = frame.meta;
            {decl_block}
                    return {cpp_body};
                }}
            }};

            extern "C" {{
                Ax::Predicate *ax_create_predicate(const char * /*params_json*/)
                {{
                    return new GeneratedPredicate_{safe}();
                }}
                void ax_destroy_predicate(Ax::Predicate *p)
                {{
                    delete p;
                }}
            }}
        """)


class PredicateCompiler:
    """Compiles an expression predicate to a shared library with g++.

    Writes predicate_<name>.cpp and predicate_<name>.so into the output directory.
    """

    def __init__(
        self,
        name: str,
        cfg: "ExprPredicateConfig",
        output_dir: Path,
        sdk_root: str,
    ) -> None:
        """Store the predicate definition and build settings.

        Args:
            name (str): Predicate name, used for the output file names.
            cfg (ExprPredicateConfig): Config holding the inputs and body.
            output_dir (Path): Directory for the generated .cpp and .so files.
            sdk_root (str): SDK root; its operators/axstreamer/include directory is added to the include path.
        """
        self._name = name
        self._cfg = cfg
        self._output_dir = output_dir
        self._sdk_root = sdk_root

    def compile(self) -> Path:
        """Transpile the predicate and build it into a shared library.

        Uses g++-12 when available, otherwise g++, with -std=c++20 -O2 -fPIC -shared. OpenCV include flags
        come from pkg-config, falling back to /usr/include/opencv4 or /usr/local/include/opencv4.

        Returns:
            Path: Path of the built .so file.

        Raises:
            ValueError: If the expression is invalid.
            RuntimeError: If g++ exits with a non-zero status; the message includes the command and stderr.
        """
        cpp_src = ExprTranspiler(
            self._name, self._cfg.inputs, self._cfg.body
        ).generate_cpp()

        src_path = self._output_dir / f"predicate_{self._name}.cpp"
        so_path = self._output_dir / f"predicate_{self._name}.so"
        src_path.write_text(cpp_src)

        sdk = Path(self._sdk_root)
        axstreamer_inc = sdk / "operators" / "axstreamer" / "include"
        pipeline_inc = Path(__file__).parent.parent.parent / "server" / "include"

        import shutil
        _gpp = shutil.which("g++-12") or "g++"
        cmd = [
            _gpp, "-std=c++20", "-O2", "-fPIC", "-shared",
            f"-I{pipeline_inc}",
            f"-I{axstreamer_inc}",
        ]
        try:
            cv_flags = subprocess.check_output(
                ["pkg-config", "--cflags", "opencv4"],
                text=True, stderr=subprocess.DEVNULL,
            ).split()
            cmd.extend(cv_flags)
        except (subprocess.CalledProcessError, FileNotFoundError):
            for _cv in [Path("/usr/include/opencv4"), Path("/usr/local/include/opencv4")]:
                if _cv.is_dir():
                    cmd.append(f"-I{_cv}")
                    break

        cmd += [str(src_path), "-o", str(so_path)]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to compile predicate '{self._name}':\n"
                f"Command: {' '.join(cmd)}\n"
                f"stderr:\n{result.stderr}"
            )
        return so_path
