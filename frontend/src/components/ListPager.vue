<template>
  <!-- athen: Previous / Next for a list, with the range of rows on screen -->
  <div class="flex shrink-0 items-center gap-1">
    <Button
      icon="lucide-chevron-left"
      :tooltip="__('Previous')"
      :disabled="loading || start <= 0"
      @click="emit('previous')"
    />
    <span class="whitespace-nowrap text-sm text-ink-gray-7">
      {{ from }}–{{ to }} / {{ totalCount }}
    </span>
    <Button
      icon="lucide-chevron-right"
      :tooltip="__('Next')"
      :disabled="loading || to >= totalCount"
      @click="emit('next')"
    />
  </div>
</template>

<script setup>
import { Button } from 'frappe-ui'
import { computed } from 'vue'

const props = defineProps({
  start: { type: Number, default: 0 },
  rowCount: { type: Number, default: 0 },
  totalCount: { type: Number, default: 0 },
  loading: { type: Boolean, default: false },
})
const emit = defineEmits(['previous', 'next'])

const from = computed(() => (props.rowCount ? props.start + 1 : 0))
const to = computed(() => props.start + props.rowCount)
</script>
