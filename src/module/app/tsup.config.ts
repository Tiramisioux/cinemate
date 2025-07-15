import { defineConfig } from 'tsup';

export default defineConfig({
    entry: ['client/src/index.ts'],
    format: ['esm'],
    sourcemap: true,
    clean: true,
    dts: true,
    platform: 'browser',
    outDir: 'static/dist',
});
