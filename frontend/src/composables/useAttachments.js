import { ref } from 'vue'
import { api } from '../services/api.js'

export function useAttachments(inputTextRef) {
  const isUploading = ref(false)
  const attachedFiles = ref([])

  async function uploadFile(file) {
    isUploading.value = true
    try {
      const res = await api.uploadFile(file)
      const data = res.data?.data
      if (data) {
        attachedFiles.value.push(data)
        if (!inputTextRef.value.trim()) {
          inputTextRef.value = data.type === 'zip'
            ? `I've uploaded a zip file: ${data.filename}. It contains extracted code. Please analyze the structure.`
            : `Analyze the files I've uploaded.`
        }
      }
    } catch (err) {
      alert(`Upload failed: ${err.response?.data?.message || err.message}`)
    } finally {
      isUploading.value = false
    }
  }

  function handleFileSelect(e) {
    const files = Array.from(e.target.files);
    e.target.value = '';
    for (const f of files) uploadFile(f)
  }
  
  function handleDrop(e) {
    const files = Array.from(e.dataTransfer.files);
    for (const f of files) uploadFile(f)
  }
  
  function removeAttachment(idx) { 
    attachedFiles.value.splice(idx, 1) 
  }

  return {
    isUploading,
    attachedFiles,
    uploadFile,
    handleFileSelect,
    handleDrop,
    removeAttachment
  }
}
