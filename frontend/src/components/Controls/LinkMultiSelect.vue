<template>
  <MultiSelect
    v-model="values"
    v-model:query="query"
    :options="options"
    :placeholder="placeholder"
    :loading="search.loading"
    :filterable="false"
    @update:open="(open) => open && (query = '')"
  />
</template>

<script setup>
import { MultiSelect, createResource } from 'frappe-ui'
import { watchDebounced } from '@vueuse/core'
import { computed, ref, watch } from 'vue'

const props = defineProps({
  doctype: { type: String, required: true },
  placeholder: { type: String, default: '' },
})

const values = defineModel({ type: Array, default: () => [] })

const query = ref('')

// labels of options seen so far, so already selected values keep their label
// once the search results move on to a different query
const labels = ref({})

// the endpoint returns 10 rows unless told otherwise; a quick filter should show
// the whole list for small masters (territories, outlets) without typing
const PAGE_LENGTH = 200

const search = createResource({
  url: 'frappe.desk.search.search_link',
  method: 'POST',
  params: { txt: '', doctype: props.doctype, page_length: PAGE_LENGTH },
  transform: (data) =>
    data.map((o) => ({ label: o.label || o.value, value: o.value })),
})

watch(
  () => search.data,
  (data) => data?.forEach((o) => (labels.value[o.value] = o.label)),
)

watchDebounced(
  [query, () => props.doctype],
  () => {
    search.update({
      params: {
        txt: query.value,
        doctype: props.doctype,
        page_length: PAGE_LENGTH,
      },
    })
    search.reload()
  },
  { debounce: 300, immediate: true },
)

// selected values are kept in the list even when the current search does not
// return them, otherwise MultiSelect drops them from its trigger summary
const options = computed(() => {
  const results = search.data || []
  const found = new Set(results.map((o) => o.value))
  const selected = values.value
    .filter((v) => !found.has(v))
    .map((v) => ({ label: labels.value[v] || v, value: v }))
  return [...selected, ...results]
})
</script>
