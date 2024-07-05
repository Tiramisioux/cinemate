import { defineConfig } from 'vitepress'

export default defineConfig({
  title: "Cinemate",
  description: "Your project description here.",
  themeConfig: {
    logo: '/path/to/logo.png',
    nav: [
      { text: 'Home', link: '/' },
      { text: 'Documentation', link: '/documentation' },
      { text: 'Team', link: '/team' },
    ],
    sidebar: [
      {
        text: 'Introduction',
        items: [
          { text: 'What is Cinemate?', link: '/what-is-cinemate' },
        ],
      },
      {
        text: 'Getting Started',
        items: [
          { text: 'Installation', link: '/installation' },
          { text: 'Usage', link: '/usage' },
        ],
      },
    ],
    socialLinks: [
      { icon: 'github', link: 'https://github.com/Tiramisioux/cinemate' },
    ],
  },
})
