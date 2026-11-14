// pages/index/index.js - 首页
const { request } = require('../../utils/api')

// 轮询间隔 800ms：成功后最多延迟不到 1 秒即可跳转（原 2000ms 白等 2 秒）
const POLL_INTERVAL = 800
const POLL_MAX_ATTEMPTS = 225

// 后端真实进度 → 前端文案与进度条
const DEFAULT_STAGE = { text: '正在理解你的食材...', percent: 12 }
const STAGE_MAP = {
  '识别中': { text: '正在识别食材...', percent: 30 },
  '搜索中': { text: '正在检索食材信息...', percent: 45 },
  '计算中': { text: '正在核算卡路里...', percent: 65 },
  '生成报告中': { text: '正在生成专属报告...', percent: 88 }
}

Page({
  data: {
    textInput: '',
    imageBase64: '',
    imagePath: '',
    hasImage: false,
    fitnessGoal: '减脂',
    loading: false,
    stageText: DEFAULT_STAGE.text,
    progressPercent: DEFAULT_STAGE.percent,
    elapsedSec: 0,
    etaSec: 12,
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

    this._setStage(DEFAULT_STAGE)
    this._startTicker()
    this.setData({ loading: true })

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
          this._stopTicker()
          this.setData({ loading: false })
          wx.setStorageSync('currentReportData', res.report_data || null)
          wx.setStorageSync('currentReport', res.report || '')
          wx.setStorageSync('currentTrace', res.tool_trace || [])
          wx.navigateTo({
            url: `/pages/report/report?time=${res.elapsed_seconds}`
          })
        } else if (res.status === 'failed') {
          this._finishWithError('分析失败', res.error || '未知错误')
        } else {
          // pending / running：跟随后端真实进度更新文案与进度条
          if (res.progress && STAGE_MAP[res.progress]) {
            this._setStage(STAGE_MAP[res.progress])
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

  _setStage(stage) {
    this.setData({ stageText: stage.text, progressPercent: stage.percent })
  },

  // 本地计时：即使后端长时间不推进度，进度条也在缓慢前进，避免「卡死」观感
  _startTicker() {
    this._stopTicker()
    this._startTime = Date.now()
    this._ticker = setInterval(() => {
      const percent = Math.min(this.data.progressPercent + 1, 95)
      this.setData({
        elapsedSec: Math.floor((Date.now() - this._startTime) / 1000),
        progressPercent: percent,
        etaSec: Math.max(Math.ceil((95 - percent) / 6), 2)
      })
    }, 1000)
  },

  _stopTicker() {
    if (this._ticker) {
      clearInterval(this._ticker)
      this._ticker = null
    }
  },

  _finishWithError(title, content) {
    this._stopTicker()
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
    this._stopTicker()
  }
})
