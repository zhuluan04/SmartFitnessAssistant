// pages/index/index.js - 首页
const { request } = require('../../utils/api')

// 轮询间隔 2 秒，最多 90 次（共 3 分钟）
const POLL_INTERVAL = 2000
const POLL_MAX_ATTEMPTS = 90

Page({
  data: {
    textInput: '',
    imageBase64: '',
    imagePath: '',
    hasImage: false,
    fitnessGoal: '减脂',
    loading: false,
    goals: [
      { label: '减脂', value: '减脂' },
      { label: '增肌', value: '增肌' },
      { label: '维持', value: '维持' }
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

  // 提交分析：创建异步任务 → 轮询结果
  onSubmit() {
    const { textInput, imageBase64, fitnessGoal, hasImage } = this.data

    if (!hasImage && !textInput.trim()) {
      wx.showToast({ title: '请输入食材或上传图片', icon: 'none' })
      return
    }

    this.setData({ loading: true })
    wx.showLoading({ title: '任务创建中...', mask: true })

    request({
      url: '/api/generate_diet/task',
      method: 'POST',
      data: {
        mode: hasImage ? 'image' : 'text',
        content: hasImage ? imageBase64 : textInput,
        fitness_goal: fitnessGoal
      }
    }).then((res) => {
      if (res.success && res.task_id) {
        this._pollTask(res.task_id, 0)
      } else {
        this._finishWithError('任务创建失败', res.error || '请稍后重试')
      }
    }).catch(() => {
      this._finishWithError('请求失败', '请检查后端服务是否启动')
    })
  },

  // 轮询任务状态：跟随后端真实进度更新提示文案
  _pollTask(taskId, attempts) {
    this._pollTimer = setTimeout(() => {
      request({
        url: `/api/generate_diet/task/${taskId}`,
        method: 'GET'
      }).then((res) => {
        if (res.status === 'success') {
          wx.hideLoading()
          this.setData({ loading: false })
          wx.setStorageSync('currentReport', res.report)
          wx.navigateTo({
            url: `/pages/report/report?time=${res.elapsed_seconds}`
          })
        } else if (res.status === 'failed') {
          this._finishWithError('分析失败', res.error || '未知错误')
        } else {
          // pending / running：更新真实进度，继续轮询
          if (res.progress) {
            wx.showLoading({ title: res.progress, mask: true })
          }
          if (attempts >= POLL_MAX_ATTEMPTS) {
            this._finishWithError('处理超时', '任务仍在后台执行，请稍后重试')
            return
          }
          this._pollTask(taskId, attempts + 1)
        }
      }).catch(() => {
        // 网络抖动不中断，继续轮询直到超时上限
        if (attempts >= POLL_MAX_ATTEMPTS) {
          this._finishWithError('请求失败', '请检查网络后重试')
        } else {
          this._pollTask(taskId, attempts + 1)
        }
      })
    }, POLL_INTERVAL)
  },

  _finishWithError(title, content) {
    wx.hideLoading()
    this.setData({ loading: false })
    wx.showModal({ title, content, showCancel: false })
  },

  onLoad() {
    // 读取保存的健身目标
    const savedGoal = wx.getStorageSync('fitnessGoal')
    if (savedGoal) {
      this.setData({ fitnessGoal: savedGoal })
    }
  },

  onUnload() {
    if (this._pollTimer) {
      clearTimeout(this._pollTimer)
      this._pollTimer = null
    }
  }
})
