// utils/api.js - 统一请求封装
const app = getApp()

/**
 * 封装 wx.request 为 Promise
 * @param {Object} options - 请求配置
 * @param {string} options.url - 接口路径（不含 baseUrl）
 * @param {string} options.method - 请求方法，默认 GET
 * @param {Object} options.data - 请求数据
 * @param {number} options.timeout - 超时时间（毫秒）
 * @returns {Promise}
 */
function request(options) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: app.globalData.apiBaseUrl + options.url,
      method: options.method || 'GET',
      data: options.data,
      timeout: options.timeout || app.globalData.requestTimeout,
      header: {
        'Content-Type': 'application/json',
        ...options.header
      },
      success: (res) => {
        if (res.statusCode === 200) {
          resolve(res.data)
        } else {
          reject(new Error(`HTTP ${res.statusCode}: ${res.data.error || '请求失败'}`))
        }
      },
      fail: (err) => {
        reject(err)
      }
    })
  })
}

/**
 * 分阶段 loading 提示
 */
let loadingTimer1 = null
let loadingTimer2 = null

function startLoading(initialText = 'Agent 思考中...') {
  wx.showLoading({ title: initialText, mask: true })

  loadingTimer1 = setTimeout(() => {
    wx.showLoading({ title: '正在搜索食谱...', mask: true })
  }, 15000)

  loadingTimer2 = setTimeout(() => {
    wx.showLoading({ title: '分析较慢，仍在处理...', mask: true })
  }, 30000)
}

function stopLoading() {
  clearTimeout(loadingTimer1)
  clearTimeout(loadingTimer2)
  loadingTimer1 = null
  loadingTimer2 = null
  wx.hideLoading()
}

module.exports = { request, startLoading, stopLoading }
