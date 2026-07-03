// pages/report/report.js - 报告页
Page({
  data: {
    reportHtml: '',
    elapsed: 0
  },

  onLoad(options) {
    const report = wx.getStorageSync('currentReport')
    this.setData({
      reportHtml: report,
      elapsed: options.time || 0
    })
  },

  // 返回首页
  goBack() {
    wx.switchTab({ url: '/pages/index/index' })
  },

  // 重新分析
  reAnalyze() {
    wx.switchTab({ url: '/pages/index/index' })
  }
})
