// pages/recommend/recommend.js - 推荐页
const { request } = require('../../utils/api')

Page({
  data: {
    recipes: [],
    currentGoal: '减脂',
    loading: false,
    goals: [
      { label: '🔥 减脂', value: '减脂' },
      { label: '💪 增肌', value: '增肌' },
      { label: '⚖️ 全部', value: '维持' }
    ]
  },

  onLoad() {
    this.loadRecipes()
  },

  onShow() {
    // 每次显示页面时刷新
    this.loadRecipes()
  },

  onFilterTap(e) {
    const goal = e.currentTarget.dataset.value
    this.setData({ currentGoal: goal })
    this.loadRecipes()
  },

  loadRecipes() {
    this.setData({ loading: true })
    
    request({
      url: `/api/recommend?goal=${this.data.currentGoal}`,
      method: 'GET'
    }).then((res) => {
      if (res.success) {
        this.setData({ recipes: res.recommendations })
      }
    }).catch(() => {
      wx.showToast({ title: '加载失败', icon: 'none' })
    }).finally(() => {
      this.setData({ loading: false })
    })
  },

  // 下拉刷新
  onPullDownRefresh() {
    this.loadRecipes()
    wx.stopPullDownRefresh()
  }
})
