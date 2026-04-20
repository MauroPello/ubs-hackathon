<script setup>
const toast = useToast()

// State
const sources = ref([])
const pending = ref(true)
const selectedSource = ref(null)
const category = ref('sql')
const docs = ref([])

// Form state
const form = reactive({
  name: '',
  type: 'sqlite',
  connection: '',
  sensitive_columns: '',
  description: '',
  upstream_mcp_server_config_id: ''
})

// Upstream configs
const { data: upstreamConfigs } = await useFetch('/api/upstream-mcp-server-configs')

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

// Fetch docs for selected source
async function fetchDocs(sourceName) {
  try {
    const data = await $fetch(`/api/data-sources/${sourceName}/docs`)
    docs.value = data
  } catch (e) {
    toast.add({ title: 'Error fetching docs', color: 'red' })
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
    sensitive_columns: form.sensitive_columns ? form.sensitive_columns.split(',').map(s => s.trim()) : []
  }

  if (category.value === 'sql') {
    payload.type = form.type
    payload.connection = form.connection
  } else {
    payload.type = category.value
    payload.connection = `upstream://${form.upstream_mcp_server_config_id}`
    payload.upstream_mcp_server_config_id = form.upstream_mcp_server_config_id
  }

  try {
    await $fetch('/api/data-sources', {
      method: 'POST',
      body: payload
    })
    toast.add({ title: 'Source created successfully', color: 'green' })
    fetchSources()
    resetForm()
  } catch (e) {
    toast.add({ title: 'Failed to create source', color: 'red' })
  }
}

function selectSource(source) {
  selectedSource.value = source
  form.name = source.name
  form.description = source.description || ''
  form.sensitive_columns = (source.sensitive_columns || []).join(', ')

  if (source.upstream_mcp_server_config_id) {
    category.value = source.type // might be 'graph' or 'documents'
    form.upstream_mcp_server_config_id = source.upstream_mcp_server_config_id
  } else {
    category.value = 'sql'
    form.type = source.type
    form.connection = source.connection
  }

  fetchDocs(source.name)
}

function resetForm() {
  selectedSource.value = null
  Object.assign(form, {
    name: '',
    type: 'sqlite',
    connection: '',
    sensitive_columns: '',
    description: '',
    upstream_mcp_server_config_id: ''
  })
}

const sqlDialects = [
  { label: 'SQLite', value: 'sqlite' },
  { label: 'PostgreSQL', value: 'postgresql' },
  { label: 'MySQL', value: 'mysql' },
  { label: 'Oracle', value: 'oracle' },
  { label: 'Snowflake', value: 'snowflake' }
]

const categories = [
  { label: 'SQL-like', value: 'sql' },
  { label: 'Graph', value: 'graph' },
  { label: 'Documents', value: 'documents' }
]
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h2 class="text-2xl font-bold text-gray-900">Sources & Documentation</h2>
        <p class="text-gray-500">Register and enrich your data catalog.</p>
      </div>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Source Form / Details -->
      <div class="space-y-6">
        <UCard>
          <template #header>
            <h3 class="font-bold">{{ selectedSource ? 'Edit Source' : 'Create New Source' }}</h3>
          </template>

          <form @submit.prevent="selectedSource ? updateSource() : createSource()" class="space-y-4">
            <UFormGroup label="Category">
              <USelectMenu v-model="category" :options="categories" />
            </UFormGroup>

            <UFormGroup label="Name" required>
              <UInput v-model="form.name" placeholder="sales_prod" />
            </UFormGroup>

            <div v-if="category === 'sql'" class="space-y-4">
              <UFormGroup label="Dialect">
                <USelectMenu v-model="form.type" :options="sqlDialects" value-attribute="value" option-attribute="label" />
              </UFormGroup>
              <UFormGroup label="Connection String">
                <UInput v-model="form.connection" placeholder="sqlite:///data/demo.db" />
              </UFormGroup>
            </div>

            <div v-else class="space-y-4">
              <UFormGroup label="Upstream MCP Server">
                <USelectMenu
                  v-model="form.upstream_mcp_server_config_id"
                  :options="upstreamConfigs || []"
                  value-attribute="id"
                  option-attribute="name"
                  placeholder="Select server..."
                />
              </UFormGroup>
            </div>

            <UFormGroup label="Sensitive Columns">
              <UInput v-model="form.sensitive_columns" placeholder="users.email, users.ssn" />
              <template #hint>Comma separated</template>
            </UFormGroup>

            <UFormGroup label="Description">
              <UTextarea v-model="form.description" />
            </UFormGroup>

            <UButton
              type="submit"
              block
              color="red"
              :label="selectedSource ? 'Update Source' : 'Create Source'"
            />
          </form>
        </UCard>

        <UCard v-if="selectedSource">
          <template #header>
            <div class="flex items-center justify-between">
              <h3 class="font-bold">Documentation</h3>
              <UButton size="xs" variant="ghost" icon="i-heroicons-plus" />
            </div>
          </template>

          <div v-if="docs.length === 0" class="text-center py-4">
            <UIcon name="i-heroicons-document-text" class="w-8 h-8 text-gray-300 mx-auto" />
            <p class="text-sm text-gray-500 mt-1">No docs yet.</p>
          </div>

          <div v-else class="space-y-3">
            <div v-for="doc in docs" :key="doc.id" class="p-3 bg-gray-50 rounded-lg border border-gray-100 relative group">
              <div class="flex items-center gap-2 mb-1">
                <UBadge size="xs" variant="solid" color="gray">{{ doc.doc_type }}</UBadge>
                <span v-if="doc.target" class="text-[10px] font-bold text-gray-400 truncate">{{ doc.target }}</span>
              </div>
              <p class="text-xs text-gray-700 line-clamp-2">{{ doc.content }}</p>
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

      <!-- Sources List -->
      <UCard class="lg:col-span-2">
        <template #header>
          <div class="flex items-center justify-between">
            <h3 class="font-bold">Registered Data Sources</h3>
            <UInput
              icon="i-heroicons-magnifying-glass-20-solid"
              size="sm"
              color="white"
              :trailing="false"
              placeholder="Search sources..."
            />
          </div>
        </template>

        <UTable
          :rows="sources"
          :columns="[
            { key: 'name', label: 'Name' },
            { key: 'type', label: 'Type' },
            { key: 'updated_at', label: 'Last Updated' },
            { key: 'actions', label: '' }
          ]"
          :loading="pending"
        >
          <template #name-data="{ row }">
            <div class="font-medium text-gray-900">{{ row.name }}</div>
            <div class="text-xs text-gray-500 truncate max-w-[200px]">{{ row.description || 'No description' }}</div>
          </template>

          <template #type-data="{ row }">
            <UBadge :color="row.upstream_mcp_server_config_id ? 'purple' : 'blue'" variant="subtle">
              {{ row.type }}
            </UBadge>
            <span v-if="row.upstream_mcp_server_config_id" class="ml-1 text-[10px] text-gray-400 uppercase font-bold">MCP</span>
          </template>

          <template #updated_at-data="{ row }">
            <span class="text-xs text-gray-500">{{ new Date(row.updated_at).toLocaleString() }}</span>
          </template>

          <template #actions-data="{ row }">
            <div class="flex justify-end gap-2">
              <UButton
                size="xs"
                color="gray"
                variant="ghost"
                icon="i-heroicons-pencil-square"
                @click="selectSource(row)"
              />
              <UButton
                size="xs"
                color="red"
                variant="ghost"
                icon="i-heroicons-trash"
              />
            </div>
          </template>
        </UTable>
      </UCard>
    </div>
  </div>
</template>
