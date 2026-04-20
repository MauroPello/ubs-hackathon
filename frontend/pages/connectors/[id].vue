<script setup>
const route = useRoute()
const router = useRouter()
const toast = useToast()

const id = route.params.id
const config = ref(null)
const registryEntry = ref(null)
const pending = ref(true)

const form = reactive({
  name: '',
  endpoint: '',
  auth: {},
  exposed_tools: []
})

async function fetchData() {
  pending.value = true
  try {
    const cfg = await $fetch(`/api/upstream-mcp-server-configs/${id}`)
    config.value = cfg
    
    const reg = await $fetch(`/api/upstream-mcp-servers/${cfg.server_id}`)
    registryEntry.value = reg
    
    // Fill form
    form.name = cfg.name
    form.endpoint = cfg.endpoint || ''
    form.auth = { ...cfg.auth }
    form.exposed_tools = [...cfg.exposed_tools]
  } catch (e) {
    toast.add({ title: 'Error fetching configuration', color: 'red' })
    router.push('/connectors')
  } finally {
    pending.value = false
  }
}

async function updateConfig() {
  const payload = {
    name: form.name,
    endpoint: form.endpoint || null,
    auth: form.auth,
    exposed_tools: form.exposed_tools
  }

  try {
    await $fetch(`/api/upstream-mcp-server-configs/${id}`, {
      method: 'PUT',
      body: payload
    })
    toast.add({ title: 'Configuration updated', color: 'green' })
    fetchData()
  } catch (e) {
    toast.add({ title: 'Failed to update configuration', color: 'red' })
  }
}

async function deleteConfig() {
  if (!confirm('Are you sure you want to delete this configuration?')) return
  
  try {
    await $fetch(`/api/upstream-mcp-server-configs/${id}`, {
      method: 'DELETE'
    })
    toast.add({ title: 'Configuration deleted', color: 'green' })
    router.push('/connectors')
  } catch (e) {
    toast.add({ title: 'Failed to delete configuration', color: 'red' })
  }
}

onMounted(() => {
  fetchData()
})
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-4">
        <UButton icon="i-heroicons-arrow-left" variant="ghost" color="gray" to="/connectors" />
        <div v-if="config">
          <h2 class="text-2xl font-bold text-gray-900">{{ config.name }}</h2>
          <p class="text-gray-500">Configured instance of {{ registryEntry?.name }}</p>
        </div>
      </div>
      <UButton color="red" variant="soft" icon="i-heroicons-trash" label="Delete Configuration" @click="deleteConfig" />
    </div>

    <div v-if="pending" class="flex items-center justify-center py-20">
      <UIcon name="i-heroicons-arrow-path" class="w-8 h-8 animate-spin text-gray-400" />
    </div>

    <div v-else class="max-w-5xl mx-auto space-y-6">
      <UCard>
        <template #header>
          <h3 class="font-bold">Edit Configuration</h3>
        </template>

        <form @submit.prevent="updateConfig" class="space-y-6">
          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <UFormGroup label="Configuration Name" required>
              <UInput v-model="form.name" placeholder="my_neo4j_prod" />
            </UFormGroup>

            <UFormGroup v-if="registryEntry?.is_mcp_tool" label="MCP endpoint">
              <UInput v-model="form.endpoint" placeholder="http://..." />
            </UFormGroup>
          </div>

          <div v-if="registryEntry?.auth_schema" class="space-y-4 border-t border-gray-100 pt-6">
            <h4 class="text-sm font-bold text-gray-400 uppercase tracking-wider">Authentication</h4>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <UFormGroup v-for="(spec, key) in registryEntry.auth_schema" :key="key" :label="key">
                <UInput 
                  v-model="form.auth[key]" 
                  :type="spec.secret ? 'password' : 'text'" 
                  :placeholder="spec.description"
                />
              </UFormGroup>
            </div>
          </div>

          <div v-if="registryEntry?.tools" class="space-y-4 border-t border-gray-100 pt-6">
            <h4 class="text-sm font-bold text-gray-400 uppercase tracking-wider">Exposed Tools</h4>
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              <div v-for="tool in registryEntry.tools" :key="tool.name" 
                   class="flex items-center gap-3 p-3 border rounded-xl hover:bg-gray-50 transition-colors">
                <UCheckbox v-model="form.exposed_tools" :value="tool.name" />
                <div class="min-w-0">
                  <p class="text-xs font-bold text-gray-900 truncate">{{ tool.name }}</p>
                  <p class="text-[10px] text-gray-500 truncate">{{ tool.description }}</p>
                </div>
              </div>
            </div>
          </div>

          <UButton type="submit" block color="red" label="Update Configuration" size="lg" />
        </form>
      </UCard>

      <!-- Server Details Info -->
      <UCard v-if="registryEntry">
        <template #header>
          <h3 class="font-bold text-gray-900">About {{ registryEntry.name }}</h3>
        </template>
        <div class="flex gap-6">
          <div class="flex-1">
            <p class="text-sm text-gray-600 leading-relaxed">{{ registryEntry.description }}</p>
            <div class="mt-4 flex gap-2">
              <UBadge color="gray" variant="subtle">{{ registryEntry.data_type }}</UBadge>
              <UBadge :color="registryEntry.status === 'available' ? 'green' : 'red'" variant="subtle">
                {{ registryEntry.status }}
              </UBadge>
            </div>
          </div>
        </div>
      </UCard>
    </div>
  </div>
</template>
