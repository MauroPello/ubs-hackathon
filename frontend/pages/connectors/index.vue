<script setup>
useHead({
  title: 'Connectors',
})

const toast = useToast()

// Data
const { data: registry } = await useFetch('/api/upstream-mcp-servers')
const { data: configs, refresh: refreshConfigs } = await useFetch('/api/upstream-mcp-server-configs')

// Form for creation
const selectedRegistry = ref(null)
const form = reactive({
  name: '',
  endpoint: '',
  auth: {},
  exposed_tools: []
})

function onServerSelect(serverId) {
  const entry = registry.value.find(e => e.id === serverId)
  selectedRegistry.value = entry
  form.name = ''
  form.endpoint = ''
  form.auth = {}
  form.exposed_tools = entry?.tools?.map(t => t.name) || []
}

async function saveConfig() {
  const payload = {
    server_id: selectedRegistry.value.id,
    name: form.name,
    endpoint: form.endpoint || null,
    auth: form.auth,
    exposed_tools: form.exposed_tools
  }

  try {
    await $fetch('/api/upstream-mcp-server-configs', {
      method: 'POST',
      body: payload
    })
    toast.add({ title: 'Configuration saved', color: 'green' })
    refreshConfigs()
    resetForm()
  } catch (e) {
    toast.add({ title: 'Failed to save configuration', color: 'red' })
  }
}

async function deleteConfig(id) {
  if (!confirm('Delete this configuration? This will also delete all associated data sources.')) return
  try {
    await $fetch(`/api/upstream-mcp-server-configs/${id}`, { method: 'DELETE' })
    toast.add({ title: 'Configuration deleted', color: 'green' })
    refreshConfigs()
  } catch (e) {
    toast.add({ title: 'Failed to delete', color: 'red' })
  }
}

function resetForm() {
  selectedRegistry.value = null
  Object.assign(form, {
    name: '',
    endpoint: '',
    auth: {},
    exposed_tools: []
  })
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold text-gray-900">Upstream Connectors</h2>
        <p class="text-gray-500">Configure and manage external data connectors.</p>
      </div>
    </div>

    <div class="space-y-6 max-w-5xl mx-auto">
      <!-- Creation Form Modal-like Card -->
      <div v-if="selectedRegistry" class="space-y-6">
        <UCard class="max-w-2xl">
          <template #header>
            <div class="flex items-center justify-between">
              <h3 class="font-bold text-gray-900">Configure New {{ selectedRegistry.name }} instance</h3>
              <UButton icon="i-heroicons-x-mark" size="xs" color="gray" variant="ghost" @click="selectedRegistry = null" />
            </div>
          </template>

          <form @submit.prevent="saveConfig" class="space-y-4">
            <UFormGroup label="Configuration Name" required>
              <UInput v-model="form.name" placeholder="my_sql_db" />
            </UFormGroup>

            <UFormGroup v-if="selectedRegistry.uses_mcp" label="MCP endpoint">
              <UInput v-model="form.endpoint" placeholder="https://..." />
            </UFormGroup>

            <div v-if="selectedRegistry.auth_schema" class="space-y-4 border-t border-gray-100 pt-4">
              <p class="text-xs font-bold text-gray-400 uppercase">Authentication</p>
              <UFormGroup v-for="(spec, key) in selectedRegistry.auth_schema" :key="key" :label="key">
                <UInput
                  v-model="form.auth[key]"
                  :type="spec.secret ? 'password' : 'text'"
                  :placeholder="spec.description"
                />
              </UFormGroup>
            </div>

            <div class="space-y-4 border-t border-gray-100 pt-4">
              <p class="text-xs font-bold text-gray-400 uppercase">Exposed Tools</p>
              <div class="max-h-40 overflow-y-auto space-y-2 pr-2">
                <div v-for="tool in selectedRegistry.tools" :key="tool.name" class="flex items-center gap-2">
                  <UCheckbox v-model="form.exposed_tools" :value="tool.name" :label="tool.name" />
                </div>
              </div>
            </div>

            <UButton type="submit" block color="red" label="Save Configuration" />
          </form>
        </UCard>
      </div>

      <!-- Registry -->
      <UCard>
        <template #header>
          <h3 class="font-bold">Available Upstream Connectors</h3>
        </template>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div v-for="entry in registry" :key="entry.id"
               class="p-4 border rounded-xl hover:border-red-300 transition-colors cursor-pointer relative group"
               @click="onServerSelect(entry.id)">
            <div class="flex items-center justify-between mb-3">
              <UBadge :color="entry.status === 'available' ? 'green' : 'red'" variant="subtle">
                {{ entry.status }}
              </UBadge>
              <UBadge color="gray" variant="solid">{{ entry.data_type }}</UBadge>
            </div>
            <h4 class="font-bold text-gray-900">{{ entry.name }}</h4>
            <p class="text-xs text-gray-500 mt-1 line-clamp-2">{{ entry.description }}</p>

            <div class="mt-4 flex flex-wrap gap-1">
              <span v-for="tool in entry.tools.slice(0, 3)" :key="tool.name" class="text-[10px] bg-gray-100 px-1.5 py-0.5 rounded text-gray-600">
                {{ tool.name }}
              </span>
              <span v-if="entry.tools.length > 3" class="text-[10px] text-gray-400 font-bold">+{{ entry.tools.length - 3 }} more</span>
            </div>

            <div class="absolute inset-0 bg-red-600/5 opacity-0 group-hover:opacity-100 transition-opacity rounded-xl flex items-center justify-center">
              <UButton label="Configure New" size="xs" color="red" />
            </div>
          </div>
        </div>
      </UCard>

      <!-- Configured Instances -->
      <UCard>
        <template #header>
          <h3 class="font-bold">Configured Instances</h3>
        </template>

        <div v-if="configs?.length === 0" class="text-center py-8">
          <p class="text-sm text-gray-500">No configured instances yet.</p>
        </div>

        <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div v-for="cfg in configs" :key="cfg.id" class="p-4 border rounded-xl bg-white hover:border-red-300 transition-all group relative flex items-center justify-between">
            <NuxtLink :to="`/connectors/${cfg.id}`" class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-1">
                <span class="font-bold text-sm text-gray-900 group-hover:text-red-600 transition-colors truncate">
                  {{ cfg.name }}
                </span>
                <UBadge size="xs" color="gray" variant="solid">{{ cfg.server_id }}</UBadge>
              </div>
              <p class="text-xs text-gray-500 truncate">{{ cfg.endpoint || 'Internal' }}</p>
            </NuxtLink>
            <div class="flex items-center gap-2">
              <UButton
                icon="i-heroicons-trash"
                size="xs"
                color="red"
                variant="ghost"
                class="opacity-0 group-hover:opacity-100 transition-opacity"
                @click.stop="deleteConfig(cfg.id)"
              />
              <UIcon name="i-heroicons-chevron-right-20-solid" class="w-5 h-5 text-gray-400 group-hover:text-red-500 transition-colors" />
            </div>
          </div>
        </div>
      </UCard>
    </div>
  </div>
</template>

