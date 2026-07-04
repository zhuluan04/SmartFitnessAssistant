// pages/profile/profile.js - 我的页
Page({
  data: {
    stats: {
      analyses: 0,
      recipes: 0,
      days: 1
    }
  },

  onLoad() {
    this.loadStats()
  },

  onShow() {
    this.loadStats()
  },

  loadStats() {
    // 从本地存储读取统计信息
    const history = wx.getStorageSync('analysisHistory') || []
    const favorites = wx.getStorageSync('favorites') || []

    // 计算使用天数（首次使用日期到今天）
    const firstUse = wx.getStorageSync('firstUseDate')
    let days = 1
    if (firstUse) {
      const first = new Date(firstUse)
      const now = new Date()
      days = Math.max(1, Math.ceil((now - first) / (1000 * 60 * 60 * 24)))
    } else {
      wx.setStorageSync('firstUseDate', new Date().toISOString())
    }

    this.setData({
      stats: {
        analyses: history.length,
        recipes: favorites.length,
        days
      }
    })
  },

  goHistory() {
    wx.showToast({ title: '功能开发中', icon: 'none' })
  },

  goFavorites() {
    wx.showToast({ title: '功能开发中', icon: 'none' })
  },

  goAbout() {
    wx.showModal({
      title: '关于',
      content: '智能健身食谱 Agent v1.0\n基于 AI 的食材识别与食谱推荐',
      showCancel: false
    })
  },

  goSettings() {
    wx.showToast({ title: '功能开发中', icon: 'none' })
  }
})
