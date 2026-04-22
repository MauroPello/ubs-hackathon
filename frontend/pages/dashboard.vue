<script setup>
useHead({
  title: 'Usage Dashboard',
})

const { data: usage, refresh: refreshUsage } = await useFetch('/api/mcp-usage')
const { data: activity, refresh: refreshActivity } = await useFetch('/api/recent-activity')

const refresh = () => {
  refreshUsage()
  refreshActivity()
}

onMounted(() => {
  const interval = setInterval(refresh, 15000)
  onUnmounted(() => clearInterval(interval))
})

const kpis = computed(() => [
  { label: 'Registered Sources', value: usage.value?.registered_sources || 0, icon: 'i-heroicons-circle-stack', color: 'blue' },
  { label: 'Stored Docs', value: usage.value?.stored_docs || 0, icon: 'i-heroicons-document-text', color: 'green' },
  { label: 'Catalog Tables', value: usage.value?.catalog_tables || 0, icon: 'i-heroicons-table-cells', color: 'purple' },
  { label: 'Requests (24h)', value: usage.value?.requests_last_24h || 0, icon: 'i-heroicons-bolt', color: 'amber' },
  { label: 'Avg Latency', value: `${usage.value?.avg_latency_ms || 0} ms`, icon: 'i-heroicons-clock', color: 'rose' },
  { label: 'Success Rate', value: `${usage.value?.success_rate_pct || 0}%`, icon: 'i-heroicons-check-circle', color: 'emerald' }
])

const trendPath = computed(() => {
  const data = usage.value?.requests_trend_7d || []
  if (data.length < 2) return ''

  const width = 400
  const height = 100
  const maxReq = Math.max(...data.map(d => d.requests), 10)
  const stepX = width / (data.length - 1)

  return data.map((d, i) => {
    const x = i * stepX
    const y = height - (d.requests / maxReq) * height
    return `${i === 0 ? 'M' : 'L'} ${x} ${y}`
  }).join(' ')
})

const timeAgo = (iso) => {
  if (!iso) return ''
  const seconds = Math.floor((new Date() - new Date(iso)) / 1000)
  if (seconds < 60) return 'Just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold text-gray-900">Connector Usage Dashboard</h2>
        <p class="text-gray-500">Real-time operational snapshot of your data ecosystem.</p>
      </div>
      <div class="flex gap-2">
        <UBadge color="green" variant="subtle" class="animate-pulse">Live Monitoring Active</UBadge>
      </div>
    </div>

    <!-- KPI Grid -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <UCard v-for="kpi in kpis" :key="kpi.label" class="hover:translate-y-[-4px] transition-transform duration-300">
        <div class="flex items-start justify-between">
          <div>
            <p class="text-sm font-medium text-gray-500">{{ kpi.label }}</p>
            <p class="text-3xl font-bold text-gray-900 mt-1">{{ kpi.value }}</p>
          </div>
          <div :class="`p-2 bg-${kpi.color}-50 rounded-lg`">
            <UIcon :name="kpi.icon" :class="`w-6 h-6 text-${kpi.color}-600`" />
          </div>
        </div>
      </UCard>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- Cool Trend Chart -->
      <UCard class="overflow-hidden">
        <template #header>
          <div class="flex items-center justify-between">
            <h3 class="font-bold">Requests Trend (Last 7 Days)</h3>
            <span class="text-xs text-gray-400 font-medium">Real-time derivation</span>
          </div>
        </template>

        <div class="relative h-48 mt-4">
          <!-- SVG Line Chart -->
          <svg viewBox="0 0 400 100" class="w-full h-full preserve-3d" preserveAspectRatio="none">
            <!-- Gradient for area under the curve -->
            <defs>
              <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="rgb(239, 68, 68)" stop-opacity="0.2" />
                <stop offset="100%" stop-color="rgb(239, 68, 68)" stop-opacity="0" />
              </linearGradient>
            </defs>

            <!-- Area under the curve -->
            <path
              v-if="trendPath"
              :d="`${trendPath} L 400 100 L 0 100 Z`"
              fill="url(#chartGradient)"
              class="transition-all duration-1000"
            />

            <!-- Main Trend Line -->
            <path
              :d="trendPath"
              fill="none"
              stroke="rgb(239, 68, 68)"
              stroke-width="2.5"
              stroke-linecap="round"
              stroke-linejoin="round"
              class="transition-all duration-1000"
            />
          </svg>

          <!-- Tooltips / Markers (Optional, but let's add labels below) -->
          <div class="absolute bottom-[-24px] left-0 right-0 flex justify-between px-1">
            <div v-for="day in usage?.requests_trend_7d" :key="day.day" class="text-[10px] font-bold text-gray-400 uppercase">
              {{ day.day }}
            </div>
          </div>
        </div>

        <!-- Detailed breakdown -->
        <div class="mt-12 space-y-3">
          <div v-for="day in usage?.requests_trend_7d" :key="day.day" class="flex items-center justify-between text-sm">
            <div class="flex items-center gap-2">
              <div class="w-2 h-2 rounded-full bg-red-500"></div>
              <span class="font-medium text-gray-600">{{ day.day }}</span>
            </div>
            <span class="font-bold text-gray-900">{{ day.requests }} requests</span>
          </div>
        </div>
      </UCard>

      <!-- Real Activity Log -->
      <UCard>
        <template #header>
          <div class="flex items-center justify-between">
            <h3 class="font-bold">Recent System Activity</h3>
            <span class="text-xs text-gray-400 font-medium">Audit logs</span>
          </div>
        </template>

        <div class="space-y-6 max-h-[500px] overflow-y-auto pr-2 custom-scrollbar">
          <div v-for="log in activity" :key="log.id" class="relative pl-6 pb-6 border-l border-gray-100 last:pb-0">
            <!-- Timeline dot -->
            <div :class="`absolute left-[-5px] top-1 w-[9px] h-[9px] rounded-full border-2 border-white ${log.status === 'Success' ? 'bg-green-500' : 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.5)]'}`"></div>

            <div class="flex items-start justify-between gap-4">
              <div class="flex-1 min-w-0">
                <p class="text-sm text-gray-900 font-semibold truncate">
                  {{ log.action }}
                </p>
                <p class="text-xs text-gray-500 mt-1">
                  {{ log.details || 'No additional details available' }}
                </p>
                <div class="mt-2 flex items-center gap-3">
                  <div class="flex items-center gap-1 text-[10px] text-gray-400 font-medium">
                    <UIcon name="i-heroicons-user" class="w-3 h-3" />
                    {{ log.actor }}
                  </div>
                  <div v-if="log.latency_ms" class="flex items-center gap-1 text-[10px] text-gray-400 font-medium">
                    <UIcon name="i-heroicons-clock" class="w-3 h-3" />
                    {{ log.latency_ms }}ms
                  </div>
                  <div class="text-[10px] text-gray-300 font-medium">
                    {{ timeAgo(log.timestamp) }}
                  </div>
                </div>
              </div>
              <UBadge size="xs" :color="log.status === 'Success' ? 'green' : 'red'" variant="subtle" class="flex-shrink-0">
                {{ log.status }}
              </UBadge>
            </div>
          </div>

          <div v-if="!activity || activity.length === 0" class="text-center py-12 text-gray-400">
            <UIcon name="i-heroicons-inbox" class="w-12 h-12 mx-auto opacity-20 mb-2" />
            <p>No activity recorded yet</p>
          </div>
        </div>
      </UCard>
    </div>
  </div>
</template>

<style scoped>
.custom-scrollbar::-webkit-scrollbar {
  width: 4px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: #f1f1f1;
  border-radius: 10px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: #e5e5e5;
}
</style>
