<script setup>
const toast = useToast()

// State
const sources = ref([])
const pending = ref(true)
const category = ref('sql')
const showCreateForm = ref(false)
const q = ref('')

// Form state
const form = reactive({
  name: '',
  databases: '',
  sensitive_columns: '',
  description: '',
  upstream_mcp_server_config_id: ''
})

// Upstream configs and servers
const { data: upstreamConfigs } = await useFetch('/api/upstream-mcp-server-configs')
const { data: upstreamServers } = await useFetch('/api/upstream-mcp-servers')

const selectedServerSpec = computed(() => {
  const config = (upstreamConfigs.value || []).find(c => c.id === form.upstream_mcp_server_config_id)
  if (!config) return null
  return (upstreamServers.value || []).find(s => s.id === config.server_id)
})

const hiddenFields = computed(() => {
  if (!selectedServerSpec.value) return []
  return selectedServerSpec.value.hidden_source_fields || []
})

// Fetch sources
async function fetchSources() {
  pending.value = true
  try {
    const data = await $fetch('/api/data-sources')
    sources.value = data
  } catch (e) {
    toast.add({ title: 'Error fetching sources', color: 'red' })
  } finally {
    pending.value = false
  }
}

onMounted(() => {
  fetchSources()
})

// Actions
async function createSource() {
  const payload = {
    name: form.name,
    description: form.description || null,
    databases: form.databases ? form.databases.split(',').map(s => s.trim()).filter(Boolean) : [],
    sensitive_columns: form.sensitive_columns ? form.sensitive_columns.split(',').map(s => s.trim()) : []
  }

  payload.upstream_mcp_server_config_id = form.upstream_mcp_server_config_id

  try {
    await $fetch('/api/data-sources', {
      method: 'POST',
      body: payload
    })
    toast.add({ title: 'Source created successfully', color: 'green' })
    fetchSources()
    resetForm()
    showCreateForm.value = false
  } catch (e) {
    toast.add({ title: 'Failed to create source', color: 'red' })
  }
}

async function deleteSource(name) {
  if (!confirm(`Are you sure you want to delete ${name}?`)) return
  try {
    await $fetch(`/api/data-sources/${name}`, { method: 'DELETE' })
    toast.add({ title: 'Source deleted', color: 'green' })
    fetchSources()
  } catch (e) {
    toast.add({ title: 'Failed to delete source', color: 'red' })
  }
}

function resetForm() {
  Object.assign(form, {
    name: '',
    databases: '',
    sensitive_columns: '',
    description: '',
    upstream_mcp_server_config_id: ''
  })
}

// No longer needed

const categories = [
  { label: 'SQL-like', value: 'sql' },
  { label: 'Graph', value: 'graph' },
  { label: 'Documents', value: 'documents' }
]

const filteredSources = computed(() => {
  if (!q.value) return sources.value
  return sources.value.filter(s => {
    return Object.values(s).some(v => String(v).toLowerCase().includes(q.value.toLowerCase()))
  })
})

</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold text-gray-900">Sources & Documentation</h2>
        <p class="text-gray-500">Register and enrich your data catalog.</p>
      </div>
      <UButton
        icon="i-heroicons-plus"
        color="red"
        label="Add Source"
        @click="showCreateForm = true"
      />
    </div>

    <div class="space-y-6 max-w-5xl mx-auto">
      <!-- Create Source Form -->
      <div v-if="showCreateForm">
        <UCard class="max-w-2xl">
          <template #header>
            <div class="flex items-center justify-between">
              <h3 class="font-bold">Create New Source</h3>
              <UButton
                icon="i-heroicons-x-mark"
                size="xs"
                color="gray"
                variant="ghost"
                @click="showCreateForm = false"
              />
            </div>
          </template>

        <form @submit.prevent="createSource()" class="space-y-4">
          <UFormGroup label="Category">
            <USelectMenu v-model="category" :options="categories" value-attribute="value" option-attribute="label" />
          </UFormGroup>

          <UFormGroup label="Name" required>
            <UInput v-model="form.name" placeholder="sales_prod" />
          </UFormGroup>

          <UFormGroup :label="`${category.charAt(0).toUpperCase() + category.slice(1)} Connector`" required>
            <USelectMenu
              v-model="form.upstream_mcp_server_config_id"
              :options="(upstreamConfigs || []).filter(c => c.data_type === category)"
              value-attribute="id"
              option-attribute="name"
              placeholder="Select connector..."
            />
          </UFormGroup>

          <UFormGroup label="Sensitive Columns" v-if="!hiddenFields.includes('sensitive_columns')">
            <UInput v-model="form.sensitive_columns" placeholder="users.email, users.ssn" />
            <template #hint>Comma separated</template>
          </UFormGroup>

          <UFormGroup label="Databases" v-if="!hiddenFields.includes('databases')">
            <UInput v-model="form.databases" placeholder="main, analytics" />
            <template #hint>Comma separated</template>
          </UFormGroup>

          <UFormGroup label="Description">
            <UTextarea v-model="form.description" />
          </UFormGroup>

          <UButton
            type="submit"
            block
            color="red"
            label="Create Source"
          />
        </form>
      </UCard>
      </div>

      <!-- Sources List -->
      <UCard :ui="{ header: { base: 'border-b-0' } }">
        <template #header>
          <div class="flex items-center justify-between">
            <h3 class="font-bold">Registered Data Sources</h3>
            <UInput
              v-model="q"
              icon="i-heroicons-magnifying-glass-20-solid"
              size="sm"
              color="white"
              :trailing="false"
              placeholder="Search sources..."
            />
          </div>
        </template>

        <UTable
          :rows="filteredSources"
          :columns="[
            { key: 'name', label: 'Name' },
            { key: 'upstream_mcp_server_config_id', label: 'Connector' },
            { key: 'updated_at', label: 'Last Updated' },
            { key: 'actions', label: '' }
          ]"
          :loading="pending"
          :ui="{ thead: 'hidden' }"
        >
          <template #name-data="{ row }">
            <NuxtLink :to="`/sources/${row.name}`" class="font-medium text-gray-900 hover:text-red-600 transition-colors">{{ row.name }}</NuxtLink>
            <div class="text-xs text-gray-500 truncate max-w-[200px]">{{ row.description || 'No description' }}</div>
          </template>

          <template #upstream_mcp_server_config_id-data="{ row }">
            <UBadge color="purple" variant="subtle">
              {{ row.upstream_mcp_server_config_id }}
            </UBadge>
          </template>

          <template #updated_at-data="{ row }">
            <span class="text-xs text-gray-500">Last Updated: {{ new Date(row.updated_at).toLocaleString() }}</span>
          </template>

          <template #actions-data="{ row }">
            <div class="flex justify-end gap-2">
              <UButton
                size="xs"
                color="gray"
                variant="ghost"
                icon="i-heroicons-pencil-square"
                :to="`/sources/${row.name}`"
              />
              <UButton
                size="xs"
                color="red"
                variant="ghost"
                icon="i-heroicons-trash"
                @click="deleteSource(row.name)"
              />
            </div>
          </template>
        </UTable>
      </UCard>
    </div>
  </div>
</template>

