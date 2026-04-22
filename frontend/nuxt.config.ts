// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  devtools: { enabled: true },
  ssr: false,
  modules: ["@nuxt/ui"],

  app: {
    head: {
      title: 'Data Source Manager',
      titleTemplate: '%s · Data Source Manager',
      link: [
        { rel: 'icon', type: 'image/avif', href: '/icon-192x192.20260313.avif', sizes: '192x192' },
        { rel: 'apple-touch-icon', href: '/apple-touch-icon-180x180.20260313.webp', sizes: '180x180' },
        { rel: 'apple-touch-icon', href: '/apple-touch-icon-167x167.20260313.webp', sizes: '167x167' },
        { rel: 'apple-touch-icon', href: '/apple-touch-icon-152x152.20260313.png', sizes: '152x152' },
        { rel: 'apple-touch-icon', href: '/apple-touch-icon-120x120.20260313.png', sizes: '120x120' },
      ],
    },
  },

  // Nuxt 4 compatibility
  future: {
    compatibilityVersion: 4,
  },

  // Color mode configuration for Nuxt UI
  colorMode: {
    preference: 'light'
  },

  // UI configuration
  ui: {
    global: true,
  },

  // Icon configuration to avoid conflict with backend proxy
  icon: {
    localApiEndpoint: '/_nuxt_icon'
  },

  // Nitro proxy for backend API during development
  nitro: {
    devProxy: {
      '/api': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
      }
    }
  },

  compatibilityDate: "2024-04-03"
})
