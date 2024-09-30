import { defineConfig } from 'vitepress'

export default {
  title: 'CineMate Documentation',
  description: 'Documentation for CineMate and its integration with CinePi raw',
  
  // Add the assetsInclude option to handle JPG files
  vite: {
    assetsInclude: ['**/*.JPG', '**/*.jpg', '**/*.png']
  },
  
  themeConfig: {
    // Your sidebar and other theme config
    sidebar: [
      {
        text: 'Introduction',
        items: [
          { text: 'Overview', link: '/overview' },
          { text: 'What is CineMate?', link: '/what-is-cinemate' },
        ],
      },
      {
        text: 'Getting Started',
        items: [
          { text: 'Hardware Requirements', link: '/hardware-requirements' },
          { text: 'Getting Started', link: '/getting-started' },
        ],
      },
      {
        text: 'Configuration',
        items: [
          { text: 'GPIO Setup', link: '/gpio-setup' },
          { text: 'Rotary Encoders', link: '/rotary-encoders' },
          { text: 'GUI', link: '/simple-gui' },
          { text: 'SSH', link: '/ssh' },
          { text: 'CLI', link: '/cli' },
          { text: 'Customizing Camera Functions and GPIO Settings', link: '/customizing' },
        ],
      },
      {
        text: 'Additional hardware',
        items: [
          { text: 'Grove Base HAT', link: '/grove-base-hat' },
          { text: 'Adafruit Quad Rotary Encoder', link: '/updating' },
        ],
      },
      {
        text: 'Advanced Features',
        items: [
          { text: 'PWM Mode', link: '/pwm-mode' },
          { text: 'Updating CineMate', link: '/updating' },
          { text: 'Audio Sync', link: '/audio-sync' },
          { text: 'RTC', link: '/rtc' },
          { text: 'Backing Up the SD Card', link: '/backup' },
        ],
      },
      {
        text: 'Examples',
        items: [
          { text: 'Builds', link: '/builds' },
          { text: 'Image Examples', link: '/images' },
        ],
      },
    ],
  },
};
