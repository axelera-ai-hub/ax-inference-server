/**
 * Rollup config that bundles Vue Flow (core, background, controls) and its CSS from `src/index.mjs`
 * into `dist/index.js`, an ES module with CSS injected at load. `vue` stays external so the page's own
 * Vue instance is used. Referenced by `pipeline_flow.py` as the `vue_flow_bundle` ESM directory.
 */
import { nodeResolve } from '@rollup/plugin-node-resolve';
import replace from '@rollup/plugin-replace';
import terser from '@rollup/plugin-terser';
import postcss from 'rollup-plugin-postcss';

export default {
  input: 'src/index.mjs',
  output: {
    file: 'dist/index.js',
    format: 'es',
  },
  // Provided by NiceGUI at runtime.
  external: ['vue'],
  plugins: [
    // Bundled libraries test process.env.NODE_ENV, which does not exist in the browser.
    replace({ preventAssignment: true, 'process.env.NODE_ENV': JSON.stringify('production') }),
    nodeResolve(),
    postcss({ inject: true, extract: false }),
    terser(),
  ],
};
