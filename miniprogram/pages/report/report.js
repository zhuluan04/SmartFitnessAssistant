// pages/report/report.js - 报告页（卡片渲染）
Page({
  data: {
    reportData: null,   // 结构化报告，优先渲染
    rawReport: '',      // JSON 解析失败时的兜底原文
    trace: [],
    elapsed: 0,
    showDebug: false
  },

  onLoad(options) {
    const data = wx.getStorageSync('currentReportData')
    const raw = wx.getStorageSync('currentReport') || ''
    const trace = wx.getStorageSync('currentTrace') || []

    // 只要后端解析出结构化结果就渲染卡片；食谱为空时由页面给出空状态提示
    const hasData = !!data

    this.setData({
      reportData: hasData ? data : null,
      rawReport: raw,
      trace,
      elapsed: options.time || 0
    })
  },

  // 工具轨迹默认折叠：普通用户不需要看到，保留给答辩演示和排查
  toggleDebug() {
    this.setData({ showDebug: !this.data.showDebug })
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
