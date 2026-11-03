<script setup lang="ts">
import { locale, setLocale } from "../i18n";
</script>
<template>
  <div class="language-switch" role="group" aria-label="Language / 语言">
    <button
      type="button"
      :aria-pressed="locale === 'zh-CN'"
      @click="setLocale('zh-CN')"
    >
      中文
    </button>
    <span aria-hidden="true">/</span>
    <button
      type="button"
      :aria-pressed="locale === 'en'"
      @click="setLocale('en')"
    >
      English
    </button>
  </div>
</template>
