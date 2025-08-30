#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI服务测试脚本
"""

import requests
import json
import time
from pathlib import Path

# 配置
API_BASE = "http://localhost:5000/api"
TEST_IMAGE_PATH = Path(__file__).parent / "test_image.jpg"

def test_health_check():
    """测试健康检查"""
    print("🔍 测试健康检查...")
    try:
        response = requests.get(f"{API_BASE}/health")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 健康检查成功: {data['message']}")
            return True
        else:
            print(f"❌ 健康检查失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 健康检查异常: {str(e)}")
        return False

def test_config():
    """测试配置获取"""
    print("⚙️ 测试配置获取...")
    try:
        response = requests.get(f"{API_BASE}/config")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 配置获取成功, 支持 {len(data['supported_styles'])} 种风格")
            return True
        else:
            print(f"❌ 配置获取失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 配置获取异常: {str(e)}")
        return False

def test_file_upload():
    """测试文件上传（需要测试图片）"""
    print("📤 测试文件上传...")
    
    if not TEST_IMAGE_PATH.exists():
        print("⚠️ 跳过文件上传测试（没有测试图片）")
        return None
    
    try:
        with open(TEST_IMAGE_PATH, 'rb') as f:
            files = {'file': f}
            data = {'type': 'image'}
            response = requests.post(f"{API_BASE}/upload", files=files, data=data)
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ 文件上传成功: {result['file_id']}")
            return result['file_id']
        else:
            print(f"❌ 文件上传失败: {response.status_code}")
            print(response.text)
            return None
    except Exception as e:
        print(f"❌ 文件上传异常: {str(e)}")
        return None

def test_api_documentation():
    """测试API文档访问"""
    print("📚 测试API文档...")
    try:
        # 测试OpenAPI JSON
        response = requests.get("http://localhost:5000/openapi.json")
        if response.status_code == 200:
            print("✅ OpenAPI JSON可访问")
        
        # 测试文档页面
        response = requests.get("http://localhost:5000/docs")
        if response.status_code == 200:
            print("✅ API文档页面可访问")
            return True
        else:
            print(f"❌ API文档访问失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ API文档访问异常: {str(e)}")
        return False

def create_test_image():
    """创建一个简单的测试图片"""
    try:
        from PIL import Image, ImageDraw
        
        # 创建一个简单的测试图片
        img = Image.new('RGB', (300, 200), color='lightblue')
        draw = ImageDraw.Draw(img)
        draw.text((50, 80), "Test Image", fill='black')
        draw.rectangle([(50, 50), (250, 150)], outline='red', width=3)
        
        img.save(TEST_IMAGE_PATH, 'JPEG', quality=85)
        print(f"✅ 创建测试图片: {TEST_IMAGE_PATH}")
        return True
    except ImportError:
        print("⚠️ PIL未安装，无法创建测试图片")
        return False
    except Exception as e:
        print(f"❌ 创建测试图片失败: {str(e)}")
        return False

def main():
    """主测试函数"""
    print("🚀 FastAPI服务测试开始")
    print("=" * 50)
    
    # 基础测试
    tests_passed = 0
    total_tests = 0
    
    # 1. 健康检查
    total_tests += 1
    if test_health_check():
        tests_passed += 1
    
    # 2. 配置获取
    total_tests += 1
    if test_config():
        tests_passed += 1
    
    # 3. API文档
    total_tests += 1
    if test_api_documentation():
        tests_passed += 1
    
    # 4. 文件上传测试（需要测试图片）
    if not TEST_IMAGE_PATH.exists():
        if create_test_image():
            total_tests += 1
            file_id = test_file_upload()
            if file_id:
                tests_passed += 1
                
                # 测试文件下载
                print("📥 测试文件下载...")
                try:
                    response = requests.get(f"{API_BASE}/files/{file_id}")
                    if response.status_code == 200:
                        print("✅ 文件下载成功")
                        tests_passed += 1
                    else:
                        print(f"❌ 文件下载失败: {response.status_code}")
                    total_tests += 1
                except Exception as e:
                    print(f"❌ 文件下载异常: {str(e)}")
                    total_tests += 1
    else:
        total_tests += 1
        file_id = test_file_upload()
        if file_id:
            tests_passed += 1
    
    # 输出测试结果
    print("\n" + "=" * 50)
    print(f"🎯 测试完成: {tests_passed}/{total_tests} 通过")
    
    if tests_passed == total_tests:
        print("🎉 所有测试通过！FastAPI服务运行正常")
        return True
    else:
        print("⚠️ 部分测试失败，请检查服务状态")
        return False

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 测试被用户中断")
    except Exception as e:
        print(f"💥 测试过程出现异常: {str(e)}")