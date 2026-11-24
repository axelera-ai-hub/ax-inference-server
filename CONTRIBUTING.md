# Contributing to ax_inference_server

First off — thank you for taking the time to contribute! 🎉

> ⚠️ **Please note:** `ax_inference_server` (Axelera Inference Server) is an **experimental reference implementation**, not an Axelera product. It is maintained on a best-effort basis with no guarantee of response times or long-term support. Contributions are very welcome, but please set expectations accordingly: reviews may take time, and not every change will be merged.

This document explains how to contribute and the rules that all contributions must follow.

## Contents

*   [Developer Certificate of Origin (DCO)](#developer-certificate-of-origin-dco)
*   [How to sign off your commits](#how-to-sign-off-your-commits)
*   [Code of Conduct](#code-of-conduct)
*   [Ways to contribute](#ways-to-contribute)
*   [Reporting bugs](#reporting-bugs)
*   [Suggesting enhancements](#suggesting-enhancements)
*   [Development setup](#development-setup)
*   [Pull request process](#pull-request-process)
*   [Commit message guidelines](#commit-message-guidelines)
*   [Coding style](#coding-style)
*   [Testing](#testing)
*   [Reporting security issues](#reporting-security-issues)
*   [License](#license)

---

## Developer Certificate of Origin (DCO)

This project uses the [Developer Certificate of Origin (DCO)](DCO) to certify that contributors have the right to submit the code they are contributing.

**By contributing to this project, you agree to and certify the terms of the DCO (version 1.1), the full text of which is in the [`DCO`](DCO) file in this repository.** In short, the DCO is a statement that you wrote the contribution yourself, or otherwise have the right to submit it under the project's [open source license](LICENSE).

We **do not** use a separate Contributor License Agreement (CLA). Instead, we require that **every commit is signed off** to indicate agreement with the DCO. Pull requests that contain commits without a valid sign-off cannot be merged.

## How to sign off your commits

Signing off is done by adding a `Signed-off-by` line to your commit message that matches the author of the commit. Git can add it for you automatically with the `-s` (or `--signoff`) flag:

```
git commit -s -m "Add an fps floor warning to the vision release test"
```

This appends a line like the following to the end of your commit message:

```
Signed-off-by: Jane Developer <jane.developer@example.com>
```

A few important points:

*   The name and email in the sign-off **must match** your Git author identity. Set them once with:

    ```
    git config --global user.name "Jane Developer"
    git config --global user.email "jane.developer@example.com"
    ```

*   Use your **real name** and a valid email address. Anonymous or pseudonymous contributions cannot satisfy the DCO.

### Fixing a missing sign-off

If you forgot to sign off, you can fix it before pushing:

```
# Amend the most recent commit
git commit --amend -s --no-edit

# Sign off every commit on your branch (rebasing off the default branch)
git rebase --signoff main
```

After amending or rebasing you will need to force-push your branch:

```
git push --force-with-lease
```

> 💡 **Tip:** Configure a Git alias or a `prepare-commit-msg` hook, or simply get into the habit of always using `git commit -s`, so you never forget the sign-off.

## Code of Conduct

Be respectful, inclusive, and constructive. Harassment, discrimination, and other unwelcome behavior will not be tolerated. Assume good intent, keep discussions technical, and help make this a welcoming space for contributors of all backgrounds and experience levels. Maintainers may remove, edit, or reject contributions and comments that do not align with these principles.

## Ways to contribute

There are many ways to help, and not all of them involve writing code:

*   Reporting bugs and reproducible issues
*   Improving documentation (typos, clarifications, new guides, examples)
*   Suggesting or prototyping enhancements
*   Testing on different hardware (Metis M.2/PCIe cards, host platforms, number of devices)
*   Reviewing open pull requests
*   Answering questions from other users

## Reporting bugs

Bugs, questions, and usage help are handled on the **[Axelera developer community](https://community.axelera.ai/)**, not through GitHub issues. See [SUPPORT.md](SUPPORT.md) for details.

Before posting:

1.  **Search the [community](https://community.axelera.ai/)** to avoid duplicates and see if your question has already been answered.
2.  Make sure you are on a supported configuration: an Ubuntu 22.04 or 24.04 host with Docker and Axelera Metis devices, set up as described in [`server/QUICKSTART.md`](server/QUICKSTART.md) and [`client/QUICKSTART.md`](client/QUICKSTART.md).

A good bug report includes:

*   A clear, descriptive title.
*   The exact steps to reproduce, ideally as a minimal example.
*   What you **expected** to happen versus what **actually** happened.
*   Relevant logs, error output, and stack traces (as text, not screenshots where possible).
*   Your environment: OS, Voyager SDK version, Metis hardware (M.2/PCIe, number of devices), whether the problem is on the server side (`host_server.py`, gRPC, vLLM) or the client side (Python clients, GUI, helper), and the output of the failing command.

If you already have a fix, you are welcome to open a pull request directly (see [Pull request process](#pull-request-process)).

## Suggesting enhancements

For non-trivial changes, **please raise the idea on the [Axelera developer community](https://community.axelera.ai/) before you start coding.** This avoids wasted effort on changes that may not fit the direction of this reference implementation. Describe the use case and motivation, not just the proposed solution — it helps others understand the problem you are solving.

## Development setup

The setup has two steps. Each step has its own quickstart:

1.  [`server/QUICKSTART.md`](server/QUICKSTART.md) sets up the server side: the Docker container, the Voyager SDK, `host_server.py`, model artifacts and vLLM.
2.  [`client/QUICKSTART.md`](client/QUICKSTART.md) sets up the client side: the Python clients, the GUI and the helper agent. Run `./setup.sh --agent --debug` there if you want to run the GUI release tests. The `--debug` flag installs Playwright and Chromium.

The scripts in [`client/examples/`](client/examples/README.md) (`vision_demo.py`, `vllm_demo.py` and `python -m helper`) are the quickest way to try a change end to end.

Typical contributor workflow:

1.  **Fork** the repository and clone your fork.

2.  Create a topic branch off `main`:

    ```
    git checkout -b my-feature main
    ```

3.  Make your changes in small, focused commits.

4.  Test locally (see [Testing](#testing)).

5.  Push to your fork and open a pull request.

Keep your branch up to date with `main` by rebasing rather than merging where practical, so history stays linear and easy to review.

## Pull request process

1.  Ensure your change **builds and the relevant release tests pass** on a host with devices (see [Testing](#testing)).
2.  Ensure **every commit is signed off** (see [above](#how-to-sign-off-your-commits)).
3.  Keep pull requests **focused and reasonably small** — one logical change per PR is far easier to review than a large, mixed changeset.
4.  Update the **documentation** when behavior changes. That means the README, the quickstarts, `client/docs/` and `server/docs/`.
5.  Fill in the PR description: explain **what** changed and **why**, and link any related [community](https://community.axelera.ai/) discussion.
6.  Be responsive to review feedback. Maintainers may request changes; push follow-up commits (or amend and force-push) as needed.
7.  By opening a PR you confirm your contribution complies with the [DCO](#developer-certificate-of-origin-dco).

## Commit message guidelines

Well-formed commit messages make history easier to read and `git blame` more useful:

*   Use a short (≤ ~72 character) **imperative** summary line: _"Add pose smoothing filter"_, not _"Added"_ or _"Adds"_.
*   Leave a blank line, then a body explaining **what** and **why** (not just how) when the change is non-trivial.
*   Reference any related [community](https://community.axelera.ai/) discussion in the body or footer.
*   End every commit with your `Signed-off-by` line (added automatically by `git commit -s`).

Example:

```
Make the cascade config always set the detector meta key

Without a meta_key_override on the detector net, the two-stage cascade
returned no detections. Set it from --detector-meta-key for both cascade
configs and add a release test that checks detections and keypoints.

Signed-off-by: Jane Developer <jane.developer@example.com>
```

## Coding style

*   **C++** (`server/src/`, `server/include/`): match the style of the surrounding code — naming, formatting, comment density — and keep the C++ standard and warnings settings of [`server/CMakeLists.txt`](server/CMakeLists.txt).
*   **Python** (`client/`, `deployment/`): follow [PEP 8](https://peps.python.org/pep-0008/) and the conventions of the file you are editing (type hints, `from __future__ import annotations`, single-quoted strings in the client code).
*   **Shell**: keep scripts idempotent, quote variables and fail fast; the setup scripts report their progress as `PHASE:` lines.
*   **gRPC contract** (`proto/`): changes to the versioned contract in `proto/axinfer/v1/` must stay backward compatible, or add a new version.
*   Keep changes minimal and avoid unrelated reformatting in the same PR.

## Testing

Most tests run against real Metis devices. Run them on a host where nothing else uses the devices.

*   **Server release suite** — runs against a running `host_server.py`. It takes about 30 seconds. It runs inside the container and reads the API key from the deployment's `.env` (see [`server/QUICKSTART.md`](server/QUICKSTART.md), section "Run the release suite"):

    ```
    docker exec "$CONTAINER" bash -c "
      cd $WORKDIR/deployment && set -a; source .env; set +a
      cd $WORKDIR/server
      HOST_SERVER_URL=http://127.0.0.1:8088 HOST_SERVER_API_KEY=\$DEPLOYMENT_API_KEY ./run_release_suite.sh
    "
    ```

*   **Client release suite** — runs against a running GUI, after `./setup.sh --debug`. It needs `HOST_SERVER_URL` and `HOST_SERVER_API_KEY` in the environment (see [`client/QUICKSTART.md`](client/QUICKSTART.md), section "Run the release suite"):

    ```
    cd client
    ./run_release_suite.sh http://127.0.0.1:8080
    ```

    The suite takes about 45 minutes on an 8-device host. Do not use the GUI while it runs. The suite also runs the `test_release_examples_*` tests. They drive [`client/examples/`](client/examples/README.md) the way a user would. A missed throughput target is a warning ("PASS with N warning(s)"), not a failure.

*   For behavioral changes, describe in the PR how you verified them: the hardware, the command and the observed result. Add or update tests where practical.

## Reporting security issues

**Please do not report security vulnerabilities publicly** — not on the [developer community](https://community.axelera.ai/) and not through GitHub. Instead, report them privately via the [Axelera support channels](https://support.axelera.ai) or by contacting the maintainers directly, and allow reasonable time for a response before public disclosure. Note that, as an experimental reference implementation, this project carries no security-support guarantees.

## License

By contributing, you agree that your contributions will be licensed under the license covering the code you are changing, and you certify the [Developer Certificate of Origin](DCO) as described above.

The code in this repository is released under the [Apache License 2.0](LICENSE). That covers only the source code in this repository — the Voyager SDK it is built on and the third-party libraries it uses (among others: vLLM, gRPC, NiceGUI, and `roboflow/trackers`) keep their own licenses. Check the license that applies to anything you bundle or vendor.
