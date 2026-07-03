// app.js - 全局配置
App({
  globalData: {
    // 开发环境地址，上线后替换为正式域名
    apiBaseUrl: 'http://localhost:8000',
    // 请求超时（毫秒），Agent 处理较慢
    requestTimeout: 60000
  },

  onLaunch() {
    // 检查后端是否在线
    this.checkBackendHealth()
  },

  checkBackendHealth() {
    wx.request({
      url: this.globalData.apiBaseUrl + '/api/health',
      method: 'GET',
      timeout: 5000,
      success: (res) => {
        if (res.data && res.data.status === 'ok') {
          console.log('后端服务在线')
        }
      },
      fail: () => {
        console.warn('后端服务未启动，部分功能不可用')
      }
    })
  }
})
