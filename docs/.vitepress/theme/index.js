// .vitepress/theme/index.js
import DefaultTheme from 'vitepress/theme'
import MyLayout from './MyLayout.vue'
import HomePage from './HomePage.vue'
import './styles/index.css'


export default {
  extends: DefaultTheme,
  Layout: MyLayout
}
    