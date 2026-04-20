<script setup>
const stats = [
  { label: 'Total Sources', value: '12', icon: 'i-heroicons-circle-stack', color: 'blue' },
  { label: 'Active Documentation', value: '48', icon: 'i-heroicons-document-text', color: 'green' },
  { label: 'API Requests (24h)', value: '1.2k', icon: 'i-heroicons-bolt', color: 'amber' },
  { label: 'System Status', value: 'Healthy', icon: 'i-heroicons-check-circle', color: 'red' }
]

const features = [
  {
    title: 'Sources & Docs',
    description: 'Register data sources, set sensitive columns, and manage documentation.',
    icon: 'i-heroicons-circle-stack',
    to: '/sources'
  },
  {
    title: 'Usage Dashboard',
    description: 'Track requests, latency, success rate, and trend data.',
    icon: 'i-heroicons-chart-bar',
    to: '/dashboard'
  },
  {
    title: 'MCP Servers',
    description: 'Register and configure upstream MCP servers like Neo4j or Notion.',
    icon: 'i-heroicons-server',
    to: '/mcp-servers'
  }
]
</script>

<template>
  <div class="space-y-8">
    <!-- Hero Section -->
    <div class="bg-gradient-to-br from-red-600 to-red-800 rounded-3xl p-8 text-white shadow-xl relative overflow-hidden">
      <div class="relative z-10">
        <h2 class="text-3xl font-bold mb-2">Welcome to Data Source Manager</h2>
        <p class="text-red-100 max-w-2xl text-lg">
          Onboard data sources, enrich schema catalogs with business documentation,
          and monitor runtime telemetry across your MCP ecosystem.
        </p>
        <div class="mt-6 flex gap-4">
          <UButton
            label="Get Started"
            size="lg"
            color="white"
            variant="solid"
            to="/sources"
          />
          <UButton
            label="Available MCP servers"
            size="lg"
            color="black"
            variant="ghost"
            to="/mcp-servers"
          />
        </div>
      </div>

      <!-- Abstract Background Element -->
      <div class="absolute -right-20 -bottom-20 w-80 h-80 bg-white/10 rounded-full blur-3xl"></div>
      <div class="absolute right-10 top-10 w-40 h-40 bg-red-400/20 rounded-full blur-2xl"></div>
    </div>

    <!-- Quick Stats -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      <UCard v-for="stat in stats" :key="stat.label" class="overflow-hidden group hover:shadow-lg transition-shadow">
        <div class="flex items-center gap-4">
          <div :class="`p-3 rounded-xl bg-${stat.color}-50 text-${stat.color}-600 transition-transform group-hover:scale-110 duration-300`">
            <UIcon :name="stat.icon" class="w-6 h-6" />
          </div>
          <div>
            <div class="text-sm font-medium text-gray-500">{{ stat.label }}</div>
            <div class="text-2xl font-bold text-gray-900">{{ stat.value }}</div>
          </div>
        </div>
      </UCard>
    </div>

    <!-- Features Grid -->
    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
      <UCard v-for="feature in features" :key="feature.title" class="hover:ring-2 hover:ring-red-500 transition-all cursor-pointer group" @click="navigateTo(feature.to)">
        <div class="p-2">
          <div class="w-12 h-12 bg-gray-100 rounded-2xl flex items-center justify-center mb-4 group-hover:bg-red-50 transition-colors">
            <UIcon :name="feature.icon" class="w-6 h-6 text-gray-600 group-hover:text-red-600" />
          </div>
          <h3 class="text-lg font-bold text-gray-900 mb-2">{{ feature.title }}</h3>
          <p class="text-gray-500 text-sm leading-relaxed">
            {{ feature.description }}
          </p>
          <div class="mt-4 flex items-center text-red-600 text-sm font-semibold">
            Explore now
            <UIcon name="i-heroicons-arrow-right" class="ml-1 w-4 h-4" />
          </div>
        </div>
      </UCard>
    </div>
  </div>
</template>
