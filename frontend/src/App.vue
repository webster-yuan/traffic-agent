<script setup lang="ts">
import { onMounted, ref } from 'vue'
import GeneratePanel from './components/GeneratePanel.vue'
import BatchPanel from './components/BatchPanel.vue'
import HistoryPanel from './components/HistoryPanel.vue'
import { useTrafficStore } from './stores/trafficStore'

const activeTab = ref<'generate' | 'batch' | 'history'>('generate')
const store = useTrafficStore()

onMounted(() => {
  store.loadIndustries()
})
</script>

<template>
  <main class="container">
    <nav class="tabs">
      <button :class="{ active: activeTab === 'generate' }" @click="activeTab = 'generate'">
        🎯 生成
      </button>
      <button :class="{ active: activeTab === 'batch' }" @click="activeTab = 'batch'">
        📦 批量
      </button>
      <button :class="{ active: activeTab === 'history' }" @click="activeTab = 'history'">
        📋 历史
      </button>
    </nav>
    <GeneratePanel v-if="activeTab === 'generate'" />
    <BatchPanel v-if="activeTab === 'batch'" />
    <HistoryPanel v-if="activeTab === 'history'" />
  </main>
</template>
