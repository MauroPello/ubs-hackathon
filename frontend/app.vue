<script setup>
const links = [{
  label: 'Overview',
  icon: 'i-heroicons-home',
  to: '/'
}, {
  label: 'Sources & Docs',
  icon: 'i-heroicons-circle-stack',
  to: '/sources'
}, {
  label: 'Usage Dashboard',
  icon: 'i-heroicons-chart-bar',
  to: '/dashboard'
}, {
  label: 'Connectors',
  icon: 'i-heroicons-server',
  to: '/connectors'
} ]
</script>

<template>
  <div class="min-h-screen bg-gray-50 flex flex-col">
    <!-- Header -->
    <header class="bg-white border-b border-gray-200 sticky top-0 z-50">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="w-9 h-9 rounded-lg overflow-hidden bg-white ring-1 ring-gray-200 flex items-center justify-center">
            <img
              src="/icon-192x192.20260313.avif"
              alt="UBS Hackathon logo"
              class="w-full h-full object-cover"
            >
          </div>
          <h1 class="text-xl font-bold text-gray-900 tracking-tight">
            Data Source Manager <span class="text-gray-400 font-normal ml-1">| UBS Hackathon</span>
          </h1>
        </div>

        <!-- <div class="flex items-center gap-4">
          <UButton
            icon="i-heroicons-bell"
            color="gray"
            variant="ghost"
          />
          <UAvatar
            src="https://github.com/nuxt.png"
            alt="User"
            size="sm"
          />
        </div> -->
      </div>
    </header>

    <div class="flex-1 flex max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8 gap-8">
      <!-- Sidebar -->
      <aside class="w-64 flex-shrink-0 hidden md:block">
        <nav class="sticky top-24">
          <UVerticalNavigation :links="links" :ui="{
            wrapper: 'space-y-1',
            base: 'group flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-md transition-colors',
            active: 'bg-red-50 text-red-600',
            inactive: 'text-gray-600 hover:bg-gray-100 hover:text-gray-900',
            icon: {
              active: 'text-red-600',
              inactive: 'text-gray-400 group-hover:text-gray-500'
            }
          }" />
        </nav>
      </aside>

      <!-- Main Content -->
      <main class="flex-1 min-w-0">
        <NuxtPage />
      </main>
    </div>

    <!-- Footer -->
    <footer class="bg-white border-t border-gray-200 py-8 mt-auto">
      <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center text-gray-500 text-sm">
        &copy; 2026 Innovation Management @ UBS.
      </div>
    </footer>

    <UNotifications />
  </div>
</template>

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

body {
  font-family: 'Inter', sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.page-enter-active,
.page-leave-active {
  transition: all 0.2s;
}
.page-enter-from,
.page-leave-to {
  opacity: 0;
  filter: blur(1rem);
}
</style>
