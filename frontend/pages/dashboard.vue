<script setup>
const { data: usage, refresh } = await useFetch('/api/mcp-usage')

// Auto-refresh every 15s
onMounted(() => {
  const interval = setInterval(refresh, 15000)
  onUnmounted(() => clearInterval(interval))
})

const kpis = computed(() => [
  { label: 'Registered Sources', value: usage.value?.registered_sources || 0, icon: 'i-heroicons-circle-stack' },
  { label: 'Stored Docs', value: usage.value?.stored_docs || 0, icon: 'i-heroicons-document-text' },
  { label: 'Catalog Tables', value: usage.value?.catalog_tables || 0, icon: 'i-heroicons-table-cells' },
  { label: 'Requests (24h)', value: usage.value?.requests_last_24h || 0, icon: 'i-heroicons-bolt' },
  { label: 'Avg Latency', value: `${usage.value?.avg_latency_ms || 0} ms`, icon: 'i-heroicons-clock' },
  { label: 'Success Rate', value: `${usage.value?.success_rate_pct || 0}%`, icon: 'i-heroicons-check-circle' }
])
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold text-gray-900">MCP Usage Dashboard</h2>
        <p class="text-gray-500">Real-time operational snapshot of your metadata ecosystem.</p>
      </div>
      <UButton
        icon="i-heroicons-arrow-path"
        label="Refresh"
        variant="ghost"
        color="gray"
        @click="refresh"
      />
    </div>

    <!-- KPI Grid -->
    <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
      <UCard v-for="kpi in kpis" :key="kpi.label">
        <div class="flex items-start justify-between">
          <div>
            <p class="text-sm font-medium text-gray-500">{{ kpi.label }}</p>
            <p class="text-3xl font-bold text-gray-900 mt-1">{{ kpi.value }}</p>
          </div>
          <div class="p-2 bg-gray-50 rounded-lg">
            <UIcon :name="kpi.icon" class="w-6 h-6 text-gray-400" />
          </div>
        </div>
        <div class="mt-4 flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider text-green-600">
          <UIcon name="i-heroicons-arrow-trending-up" />
          <span>Stable</span>
        </div>
      </UCard>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- Trend List -->
      <UCard>
        <template #header>
          <h3 class="font-bold">Requests Trend (Last 7 Days)</h3>
        </template>
        
        <div class="space-y-4">
          <div v-for="day in usage?.requests_trend_7d" :key="day.day" class="flex items-center gap-4">
            <div class="w-20 text-sm font-medium text-gray-600">{{ day.day }}</div>
            <div class="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
              <div 
                class="h-full bg-red-500 rounded-full transition-all duration-1000"
                :style="{ width: `${(day.requests / 100) * 100}%` }"
              ></div>
            </div>
            <div class="w-16 text-right text-sm font-bold text-gray-900">{{ day.requests }} req</div>
          </div>
        </div>
      </UCard>

      <!-- System Logs / Activity -->
      <UCard>
        <template #header>
          <h3 class="font-bold">Recent System Activity</h3>
        </template>
        
        <div class="space-y-4">
          <div v-for="i in 5" :key="i" class="flex gap-4">
            <div class="flex-shrink-0 w-8 h-8 rounded-full bg-gray-100 flex items-center justify-center">
              <UIcon name="i-heroicons-user" class="w-4 h-4 text-gray-500" />
            </div>
            <div class="flex-1 min-w-0">
              <p class="text-sm text-gray-900">
                <span class="font-bold">System</span> updated catalog for <span class="text-red-600">sales_sqlite_prod</span>
              </p>
              <p class="text-xs text-gray-500">2 hours ago</p>
            </div>
            <UBadge size="xs" color="gray" variant="subtle">Success</UBadge>
          </div>
        </div>
      </UCard>
    </div>
  </div>
</template>
