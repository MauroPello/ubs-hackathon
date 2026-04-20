// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  devtools: { enabled: true },
  ssr: false,
  modules: ["@nuxt/ui"],
  
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
