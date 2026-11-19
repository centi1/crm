<template>
  <FormControl
    v-if="filter.fieldtype == 'Check'"
    v-model="filter.value"
    :label="filter.label"
    type="checkbox"
    @change.stop="updateFilter(filter, $event.target.checked)"
  />
  <!-- athen: drop-down quick filters take several values -->
  <MultiSelect
    v-else-if="filter.fieldtype === 'Select'"
    :model-value="Array.isArray(filter.value) ? filter.value : []"
    :options="(filter.options || []).filter((o) => o.value)"
    :placeholder="filter.label"
    @update:modelValue="(v) => updateFilter(filter, v)"
  />
  <LinkMultiSelect
    v-else-if="filter.fieldtype === 'Link'"
    :model-value="Array.isArray(filter.value) ? filter.value : []"
    :doctype="filter.options"
    :placeholder="filter.label"
    @update:modelValue="(v) => updateFilter(filter, v)"
  />
  <!-- athen: a date quick filter takes a from-to range (one day = the same date twice) -->
  <DateRangePicker
    v-else-if="['Date', 'Datetime'].includes(filter.fieldtype)"
    class="min-w-52 border-none"
    :model-value="Array.isArray(filter.value) ? filter.value : []"
    :placeholder="filter.label"
    :format="getFormat('', '', true, false, false)"
    @change="(v) => updateFilter(filter, v)"
  />
  <FormControl
    v-else
    v-model="filter.value"
    type="text"
    :placeholder="filter.label"
    @input.stop="debouncedFn(filter, $event.target.value)"
  />
</template>
<script setup>
import LinkMultiSelect from '@/components/Controls/LinkMultiSelect.vue'
import { FormControl, DateRangePicker, MultiSelect } from 'frappe-ui'
import { getFormat } from '@/utils'
import { useDebounceFn } from '@vueuse/core'
import { reactive, watch } from 'vue'

const props = defineProps({
  filter: { type: Object, required: true },
})

const filter = reactive(props.filter)

const emit = defineEmits(['applyQuickFilter'])

watch(
  () => props.filter,
  (newFilter) => Object.assign(filter, newFilter),
  { deep: true },
)

const debouncedFn = useDebounceFn((f, value) => {
  emit('applyQuickFilter', f, value)
}, 500)

function updateFilter(f, value) {
  emit('applyQuickFilter', f, value)
}
</script>
