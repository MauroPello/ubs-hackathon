<script setup>
const toast = useToast()

// Data
const { data: registry } = await useFetch('/api/upstream-mcp-servers')
const { data: configs, refresh: refreshConfigs } = await useFetch('/api/upstream-mcp-server-configs')

// Form
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
        <h2 class="text-2xl font-bold text-gray-900">Upstream MCP Servers</h2>
        <p class="text-gray-500">Configure and manage external MCP connectors.</p>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Registry -->
      <UCard class="lg:col-span-2">
        <template #header>
          <h3 class="font-bold">Available Upstream Servers</h3>
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
              <UButton label="Configure" size="xs" color="red" />
            </div>
          </div>
        </div>

        <template #footer>
          <div class="flex items-center justify-between text-xs text-gray-400">
            <span>Total registry entries: {{ registry?.length }}</span>
            <span>Last sync: Just now</span>
          </div>
        </template>
      </UCard>

      <!-- Config Form -->
      <div class="space-y-6">
        <UCard v-if="selectedRegistry">
          <template #header>
            <div class="flex items-center justify-between">
              <h3 class="font-bold">Configure {{ selectedRegistry.name }}</h3>
              <UButton icon="i-heroicons-x-mark" size="xs" color="gray" variant="ghost" @click="selectedRegistry = null" />
            </div>
          </template>

          <form @submit.prevent="saveConfig" class="space-y-4">
            <UFormGroup label="Configuration Name" required>
              <UInput v-model="form.name" placeholder="my_neo4j_prod" />
            </UFormGroup>

            <UFormGroup label="Endpoint URL">
              <UInput v-model="form.endpoint" placeholder="http://..." />
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

        <UCard v-else>
          <template #header>
            <h3 class="font-bold">Configured Instances</h3>
          </template>
          
          <div v-if="configs?.length === 0" class="text-center py-8">
            <p class="text-sm text-gray-500">No configured instances yet.</p>
          </div>
          
          <div v-else class="space-y-3">
            <div v-for="cfg in configs" :key="cfg.id" class="p-3 border rounded-lg bg-gray-50 group relative">
              <div class="flex items-center justify-between mb-1">
                <span class="font-bold text-sm text-gray-900">{{ cfg.name }}</span>
                <UBadge size="xs" color="gray" variant="solid">{{ cfg.server_id }}</UBadge>
              </div>
              <p class="text-[10px] text-gray-500 truncate">{{ cfg.endpoint || 'Internal' }}</p>
              
              <UButton
                class="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity"
                size="xs"
                color="red"
                variant="ghost"
                icon="i-heroicons-trash"
              />
            </div>
          </div>
        </UCard>
      </div>
    </div>
  </div>
</template>
