// pages/profile/profile.js - 我的页
Page({
  data: {
    currentGoal: '减脂',
    goals: [
      { icon: '🔥', label: '减脂', value: '减脂' },
      { icon: '💪', label: '增肌', value: '增肌' },
      { icon: '⚖️', label: '维持', value: '维持' }
    ]
  },

  onLoad() {
    const saved = wx.getStorageSync('fitnessGoal')
    if (saved) {
      this.setData({ currentGoal: saved })
    }
  },

  onGoalTap(e) {
    const goal = e.currentTarget.dataset.value
    this.setData({ currentGoal: goal })
    wx.setStorageSync('fitnessGoal', goal)
    wx.showToast({ title: `目标已设为${goal}`, icon: 'success' })
  },

  goHistory() {
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
