"""
日志系统模块
支持按 user_id 分离日志文件，带时间戳
"""
import logging
import os
from datetime import datetime


# 日志目录
LOG_DIR = "logs"


# ------------------------------------------------------------
# get_logger
# 功能: 获取指定 user_id 的 logger，支持输出到终端和文件
# ------------------------------------------------------------
def get_logger(user_id: str = "default", log_to_file: bool = True, log_to_console: bool = True, level: int = logging.DEBUG) -> logging.Logger:
    """
    获取指定 user_id 的 logger。

    Args:
        user_id: 用户 ID (str)，每个用户有独立的日志文件
        log_to_file: 是否输出到文件 (bool)，默认 True
        log_to_console: 是否输出到终端 (bool)，默认 True
        level: 日志级别 (int)，默认 logging.DEBUG

    Returns:
        logging.Logger: 配置好的 logger
    """
    # 创建 logs 目录
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    # logger 名称：user_logger_{user_id}
    logger_name = f"user_logger_{user_id}"
    logger = logging.getLogger(logger_name)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    # 设置日志级别
    logger.setLevel(level)

    # 日志格式：时间 | 级别 | 消息
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 终端 handler
    if log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    # 文件 handler
    if log_to_file:
        log_file = os.path.join(LOG_DIR, f"{user_id}.log")
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# ------------------------------------------------------------
# setup_global_logger
# 功能: 设置全局 logger（不按用户分离），用于启动阶段
# ------------------------------------------------------------
def setup_global_logger(log_to_file: bool = True, log_to_console: bool = True, level: int = logging.DEBUG, clear_previous_logs: bool = False) -> logging.Logger:
    """
    设置全局 logger，用于启动阶段（还没有 user_id 时）。

    Args:
        log_to_file: 是否输出到文件 (bool)，默认 True
        log_to_console: 是否输出到终端 (bool)，默认 True
        level: 日志级别 (int)，默认 logging.DEBUG
        clear_previous_logs: 是否清空之前的日志文件 (bool)，默认 False

    Returns:
        logging.Logger: 配置好的 logger
    """
    # 创建 logs 目录
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR)

    # 如果需要清空之前的日志，在创建文件处理器之前执行
    if clear_previous_logs:
        clear_log_files()

    logger = logging.getLogger("global_logger")

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    logger.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    if log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    if log_to_file:
        log_file = os.path.join(LOG_DIR, "global.log")
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


# ------------------------------------------------------------
# clear_log_files
# 功能: 清空所有日志文件，在应用启动时调用
# ------------------------------------------------------------
def clear_log_files():
    """
    清空 logs 目录下的所有 .log 文件。
    在应用启动时调用，确保每次运行都是新的日志。
    """
    if not os.path.exists(LOG_DIR):
        return

    for filename in os.listdir(LOG_DIR):
        if filename.endswith(".log"):
            log_file = os.path.join(LOG_DIR, filename)
            try:
                with open(log_file, "w", encoding="utf-8") as f:
                    f.write("")  # 清空文件内容
            except Exception as e:
                print(f"[WARNING] 清空日志文件失败 {filename}: {e}")
