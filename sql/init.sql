-- 初始化数据库与表结构（可重复执行，不会报错）
CREATE DATABASE IF NOT EXISTS fitness_db DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE fitness_db;

-- 食谱生成异步任务表
CREATE TABLE IF NOT EXISTS diet_tasks (
    task_id    VARCHAR(32) PRIMARY KEY COMMENT '任务唯一 ID',
    status     VARCHAR(16) NOT NULL DEFAULT 'pending' COMMENT 'pending/running/success/failed',
    progress   VARCHAR(32) DEFAULT NULL COMMENT '进度节点',
    result     JSON DEFAULT NULL COMMENT '成功结果',
    error      TEXT DEFAULT NULL COMMENT '失败原因',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status (status),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='食谱生成异步任务';

-- 精选推荐食谱表
CREATE TABLE IF NOT EXISTS recommendations (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    name             VARCHAR(64) NOT NULL,
    calories         VARCHAR(16) NOT NULL,
    tags             JSON NOT NULL,
    description      TEXT NOT NULL,
    nutrition_score  TINYINT NOT NULL DEFAULT 0,
    difficulty_score TINYINT NOT NULL DEFAULT 0,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='精选推荐食谱';

-- 初始数据（INSERT IGNORE 保证重复执行不报错）
INSERT IGNORE INTO recommendations (id, name, calories, tags, description, nutrition_score, difficulty_score) VALUES
(1, '鸡胸肉西兰花便当', '311 kcal', JSON_ARRAY('高蛋白','低脂','减脂推荐'), '鸡胸肉切块腌制后滑炒，西兰花焯水备用，鸡蛋炒散，三者混合加蒜蓉调味翻炒均匀即可出锅。', 9, 8),
(2, '三文鱼牛油果沙拉', '368 kcal', JSON_ARRAY('优质脂肪','增肌推荐','无需烹饪'), '三文鱼煎至两面金黄切块，牛油果切片，搭配混合生菜，淋柠檬汁和橄榄油即可。', 9, 9),
(3, '番茄虾仁豆腐汤', '193 kcal', JSON_ARRAY('低卡','高蛋白','减脂推荐'), '番茄切块炒出汁水，加水煮沸后放入豆腐块和虾仁，煮至虾仁变色，盐和胡椒调味。', 8, 9),
(4, '糙米饭牛肉碗', '366 kcal', JSON_ARRAY('碳水补充','增肌推荐','饱腹感强'), '牛肉切片腌制快炒，搭配糙米饭、焯水的菠菜和胡萝卜丝，浇上低盐酱油汁。', 8, 7),
(5, '红薯燕麦能量碗', '463 kcal', JSON_ARRAY('早餐推荐','膳食纤维','慢释放碳水'), '红薯蒸熟切丁，燕麦用牛奶煮软，加入红薯丁和少许蜂蜜，撒上坚果碎。', 8, 10),
(6, '黄瓜鸡胸肉凉面', '249 kcal', JSON_ARRAY('低卡','夏日推荐','清爽'), '鸡胸肉煮熟撕丝，黄瓜切丝，荞麦面煮熟过凉水，淋芝麻酱和醋汁拌匀。', 7, 8);
