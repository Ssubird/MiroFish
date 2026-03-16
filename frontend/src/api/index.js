import axios from 'axios'

const service = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:5001',
  timeout: 300000,
  headers: {
    'Content-Type': 'application/json'
  }
})

service.interceptors.request.use(
  config => config,
  error => Promise.reject(error)
)

service.interceptors.response.use(
  response => {
    const res = response.data
    if (!res.success && res.success !== undefined) {
      return Promise.reject(new Error(res.error || res.message || 'Error'))
    }
    return res
  },
  error => {
    const backendMessage = error.response?.data?.error
    if (backendMessage) {
      error.message = backendMessage
    }
    return Promise.reject(error)
  }
)

export const requestWithRetry = async (requestFn, maxRetries = 3, delay = 1000) => {
  for (let i = 0; i < maxRetries; i += 1) {
    try {
      return await requestFn()
    } catch (error) {
      if (i === maxRetries - 1) {
        throw error
      }
      await new Promise(resolve => setTimeout(resolve, delay * Math.pow(2, i)))
    }
  }
}

export default service
