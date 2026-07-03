// pages/index/index.js - 首页
const { request, startLoading, stopLoading } = require('../../utils/api')

Page({
  data: {
    textInput: '',
    imageBase64: '',
    imagePath: '',
    hasImage: false,
    fitnessGoal: '减脂',
    loading: false,
    goals: [
      { label: '🔥 减脂', value: '减脂' },
      { label: '💪 增肌', value: '增肌' },
      { label: '⚖️ 维持', value: '维持' }
    ]
  },

  onTextInput(e) {
    this.setData({ textInput: e.detail.value })
  },

  onGoalTap(e) {
    this.setData({ fitnessGoal: e.currentTarget.dataset.value })
    wx.setStorageSync('fitnessGoal', e.currentTarget.dataset.value)
  },

  // 选择并压缩图片
  chooseImage() {
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      success: (res) => {
        const tempPath = res.tempFiles[0].tempFilePath
        const size = res.tempFiles[0].size
        
        // 限制 4MB
        if (size > 4 * 1024 * 1024) {
          wx.showToast({ title: '图片不能超过4MB', icon: 'none' })
          return
        }
        
        // 压缩图片
        wx.compressImage({
          src: tempPath,
          quality: 70,
          success: (compressed) => {
            const fs = wx.getFileSystemManager()
            const base64 = fs.readFileSync(compressed.tempFilePath, 'base64')
            this.setData({
              imageBase64: base64,
              imagePath: compressed.tempFilePath,
              hasImage: true
            })
          }
        })
      }
    })
  },

  removeImage() {
    this.setData({
      imageBase64: '',
      imagePath: '',
      hasImage: false
    })
  },

  // 提交分析
  onSubmit() {
    const { textInput, imageBase64, fitnessGoal, hasImage } = this.data
    
    if (!hasImage && !textInput.trim()) {
      wx.showToast({ title: '请输入食材或上传图片', icon: 'none' })
      return
    }
    
    this.setData({ loading: true })
    startLoading()
    
    request({
      url: '/api/generate_diet',
      method: 'POST',
      data: {
        mode: hasImage ? 'image' : 'text',
        content: hasImage ? imageBase64 : textInput,
        fitness_goal: fitnessGoal
      }
    }).then((res) => {
      stopLoading()
      if (res.success) {
        wx.setStorageSync('currentReport', res.report)
        wx.navigateTo({
          url: `/pages/report/report?time=${res.elapsed_seconds}`
        })
      } else {
        wx.showModal({
          title: '分析失败',
          content: res.error,
          showCancel: false
        })
      }
    }).catch((err) => {
      stopLoading()
      wx.showModal({
        title: '请求失败',
        content: '请检查后端服务是否启动',
        showCancel: false
      })
    }).finally(() => {
      this.setData({ loading: false })
    })
  },

  onLoad() {
    // 读取保存的健身目标
    const savedGoal = wx.getStorageSync('fitnessGoal')
    if (savedGoal) {
      this.setData({ fitnessGoal: savedGoal })
    }
  }
})
