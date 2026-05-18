/* Wait until *everything* is parsed and scripts are in place */
window.addEventListener('load', () => {
  if (typeof hljs === 'undefined') {
    console.warn('Highlight.js not found');
    return;
  }
  if (typeof CopyButtonPlugin === 'undefined') {
    console.warn('highlightjs-copy plugin not found');
    return;
  }

    /* Attach the plugin */
    hljs.addPlugin(new CopyButtonPlugin({
        autohide: true             // keep the button visible
    }));

    /* (Re)highlight so the plugin wraps existing <pre><code> blocks */
    hljs.highlightAll();
});
