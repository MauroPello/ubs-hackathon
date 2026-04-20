<script setup>
const route = useRoute()
const router = useRouter()
const toast = useToast()

const name = route.params.name
const source = ref(null)
const docs = ref([])
const pending = ref(true)

// Form state
const category = ref('sql')
const form = reactive({
  name: '',
  type: 'sqlite',
  connection: '',
  sensitive_columns: '',
  description: '',
  upstream_mcp_server_config_id: ''
})

// Doc form state
const showDocModal = ref(false)
const editingDocId = ref(null)
const docForm = reactive({
  doc_type: 'table',
  target: '',
  content: ''
})

// Upstream configs
const { data: upstreamConfigs } = await useFetch('/api/upstream-mcp-server-configs')

async function fetchData() {
  pending.value = true
  try {
    const [sourceData, docsData] = await Promise.all([
      $fetch(`/api/data-sources/${name}`),
      $fetch(`/api/data-sources/${name}/docs`)
    ])

    source.value = sourceData
    docs.value = docsData

    // Fill form
    form.name = sourceData.name
    form.description = sourceData.description || ''
    form.sensitive_columns = (sourceData.sensitive_columns || []).join(', ')

    if (sourceData.upstream_mcp_server_config_id) {
      category.value = sourceData.type
      form.upstream_mcp_server_config_id = sourceData.upstream_mcp_server_config_id
    } else {
      category.value = 'sql'
      form.type = sourceData.type
      form.connection = sourceData.connection
    }
  } catch (e) {
    toast.add({ title: 'Error fetching data source', color: 'red' })
    router.push('/sources')
  } finally {
    pending.value = false
  }
}

async function updateSource() {
  const payload = {
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
    await $fetch(`/api/data-sources/${name}`, {
      method: 'PUT',
      body: payload
    })
    toast.add({ title: 'Source updated successfully', color: 'green' })
    fetchData()
  } catch (e) {
    toast.add({ title: 'Failed to update source', color: 'red' })
  }
}

async function deleteSource() {
  if (!confirm('Are you sure you want to delete this data source?')) return

  try {
    await $fetch(`/api/data-sources/${name}`, {
      method: 'DELETE'
    })
    toast.add({ title: 'Source deleted', color: 'green' })
    router.push('/sources')
  } catch (e) {
    toast.add({ title: 'Failed to delete source', color: 'red' })
  }
}

async function addDoc() {
  try {
    if (editingDocId.value) {
      await $fetch(`/api/data-sources/${name}/docs/${editingDocId.value}`, {
        method: 'PUT',
        body: docForm
      })
      toast.add({ title: 'Documentation updated', color: 'green' })
    } else {
      await $fetch(`/api/data-sources/${name}/docs`, {
        method: 'POST',
        body: docForm
      })
      toast.add({ title: 'Documentation added', color: 'green' })
    }
    showDocModal.value = false
    resetDocForm()
    fetchData()
  } catch (e) {
    toast.add({ title: `Failed to ${editingDocId.value ? 'update' : 'add'} documentation`, color: 'red' })
  }
}

function resetDocForm() {
  editingDocId.value = null
  docForm.doc_type = 'table'
  docForm.target = ''
  docForm.content = ''
}

function openAddDocModal() {
  resetDocForm()
  showDocModal.value = true
}

function openEditDocModal(doc) {
  editingDocId.value = doc.id
  docForm.doc_type = doc.doc_type
  docForm.target = doc.target || ''
  docForm.content = doc.content
  showDocModal.value = true
}

async function removeDoc(docId) {
  try {
    await $fetch(`/api/data-sources/${name}/docs/${docId}`, {
      method: 'DELETE'
    })
    toast.add({ title: 'Documentation removed', color: 'green' })
    fetchData()
  } catch (e) {
    toast.add({ title: 'Failed to remove documentation', color: 'red' })
  }
}

onMounted(() => {
  fetchData()
})

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

const docTypes = [
  { label: 'Table', value: 'table' },
  { label: 'Column', value: 'column' },
  { label: 'Graph Entity', value: 'graph_entity' },
  { label: 'Graph Property', value: 'graph_property' }
]
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div class="flex items-center gap-4">
        <UButton icon="i-heroicons-arrow-left" variant="ghost" color="gray" to="/sources" />
        <div>
          <h2 class="text-2xl font-bold text-gray-900">{{ name }}</h2>
          <p class="text-gray-500">Manage source details and documentation.</p>
        </div>
      </div>
      <UButton color="red" variant="soft" icon="i-heroicons-trash" label="Delete Source" @click="deleteSource" />
    </div>

    <div v-if="pending" class="flex items-center justify-center py-20">
      <UIcon name="i-heroicons-arrow-path" class="w-8 h-8 animate-spin text-gray-400" />
    </div>

    <div v-else class="space-y-6 max-w-5xl mx-auto">
      <UCard>
        <template #header>
          <h3 class="font-bold">Edit Source</h3>
        </template>

        <form @submit.prevent="updateSource" class="space-y-4">
          <UFormGroup label="Category">
            <USelectMenu v-model="category" :options="categories" value-attribute="value" option-attribute="label" />
          </UFormGroup>

          <UFormGroup label="Name" required>
            <UInput v-model="form.name" disabled />
            <template #hint>Names cannot be changed</template>
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
            label="Update Source"
          />
        </form>
      </UCard>

      <UCard>
        <template #header>
          <div class="flex items-center justify-between">
            <h3 class="font-bold">Documentation</h3>
            <UButton label="Add" size="sm" variant="ghost" icon="i-heroicons-plus" @click="openAddDocModal" />
          </div>
        </template>

        <div v-if="docs.length === 0" class="text-center py-10 border-2 border-dashed border-gray-100 rounded-xl">
          <UIcon name="i-heroicons-document-text" class="w-12 h-12 text-gray-200 mx-auto" />
          <p class="text-sm text-gray-500 mt-2">No documentation entries yet.</p>
          <UButton variant="link" color="red" label="Add first entry" @click="openAddDocModal" />
        </div>

        <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div
            v-for="doc in docs"
            :key="doc.id"
            class="p-4 bg-gray-50 rounded-xl border border-gray-100 relative group hover:border-red-200 transition-colors cursor-pointer"
            @click="openEditDocModal(doc)"
          >
            <div class="flex items-center gap-2 mb-2">
              <UBadge size="xs" variant="solid" color="gray">{{ doc.doc_type }}</UBadge>
              <span v-if="doc.target" class="text-[10px] font-bold text-gray-400 truncate">{{ doc.target }}</span>
            </div>
            <p class="text-sm text-gray-700">{{ doc.content }}</p>
            <UButton
              class="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity"
              size="xs"
              color="red"
              variant="ghost"
              icon="i-heroicons-trash"
              @click.stop="removeDoc(doc.id)"
            />
          </div>
        </div>
      </UCard>
    </div>

    <!-- Add Doc Modal -->
    <UModal v-model="showDocModal">
      <UCard>
        <template #header>
          <div class="flex items-center justify-between">
            <h3 class="font-bold">{{ editingDocId ? 'Edit Documentation' : 'Add Documentation' }}</h3>
            <UButton color="gray" variant="ghost" icon="i-heroicons-x-mark" @click="showDocModal = false" />
          </div>
        </template>

        <form @submit.prevent="addDoc" class="space-y-4">
          <UFormGroup label="Type">
            <USelectMenu v-model="docForm.doc_type" :options="docTypes" value-attribute="value" option-attribute="label" />
          </UFormGroup>

          <UFormGroup label="Target (Table/Column/Entity)">
            <UInput v-model="docForm.target" placeholder="users.email or customers" />
            <template #hint>Leave empty for global source docs</template>
          </UFormGroup>

          <UFormGroup label="Content" required>
            <UTextarea v-model="docForm.content" placeholder="Description of the target..." />
          </UFormGroup>

          <UButton type="submit" block color="red" :label="editingDocId ? 'Update Documentation' : 'Add Documentation'" />
        </form>
      </UCard>
    </UModal>
  </div>
</template>
