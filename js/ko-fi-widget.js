if (document.getElementById('ko-fi-container')) {
  const script = document.createElement('script');
  script.src = 'https://storage.ko-fi.com/cdn/widget/Widget_2.js';
  script.onload = () => {
    kofiwidget2.init('Support Cinemate on Ko-fi', '#72a4f2', 'G2G21IM9RO');
    kofiwidget2.draw();
  };
  document.getElementById('ko-fi-container').appendChild(script);
}
