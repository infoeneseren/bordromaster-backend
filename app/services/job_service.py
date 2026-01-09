# -*- coding: utf-8 -*-
"""
Job Service - Background Mail Gönderim İşleri
- Redis ile job state yönetimi
- Async mail gönderimi
- İlerleme takibi
"""

import json
import uuid
import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
from enum import Enum
import redis.asyncio as redis

from app.core.config import settings


class JobStatus(str, Enum):
    """Job durumları"""
    PENDING = "pending"      # Kuyrukta bekliyor
    RUNNING = "running"      # Çalışıyor
    COMPLETED = "completed"  # Tamamlandı
    FAILED = "failed"        # Hata oluştu


class JobService:
    """Background job yönetim servisi"""
    
    def __init__(self):
        self._redis: Optional[redis.Redis] = None
    
    async def get_redis(self) -> redis.Redis:
        """Redis bağlantısını al veya oluştur"""
        if self._redis is None:
            self._redis = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
        return self._redis
    
    async def close(self):
        """Redis bağlantısını kapat"""
        if self._redis:
            await self._redis.close()
            self._redis = None
    
    async def create_job(
        self,
        job_type: str,
        total_items: int,
        company_id: int,
        user_id: int,
        metadata: Optional[Dict] = None
    ) -> str:
        """Yeni job oluştur ve ID döndür"""
        job_id = str(uuid.uuid4())
        
        job_data = {
            "id": job_id,
            "type": job_type,
            "status": JobStatus.PENDING.value,
            "company_id": company_id,
            "user_id": user_id,
            "total": total_items,
            "completed": 0,
            "success_count": 0,
            "error_count": 0,
            "results": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": None,
            "finished_at": None,
            "metadata": metadata or {}
        }
        
        r = await self.get_redis()
        # 24 saat sonra expire
        await r.setex(f"job:{job_id}", 86400, json.dumps(job_data))
        
        return job_id
    
    async def get_job(self, job_id: str) -> Optional[Dict]:
        """Job bilgilerini getir"""
        r = await self.get_redis()
        data = await r.get(f"job:{job_id}")
        if data:
            return json.loads(data)
        return None
    
    async def update_job(
        self,
        job_id: str,
        status: Optional[JobStatus] = None,
        completed: Optional[int] = None,
        success_count: Optional[int] = None,
        error_count: Optional[int] = None,
        result: Optional[Dict] = None,
        error_message: Optional[str] = None
    ):
        """Job durumunu güncelle"""
        r = await self.get_redis()
        data = await r.get(f"job:{job_id}")
        if not data:
            return
        
        job = json.loads(data)
        
        if status:
            job["status"] = status.value
            if status == JobStatus.RUNNING and not job["started_at"]:
                job["started_at"] = datetime.now(timezone.utc).isoformat()
            elif status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                job["finished_at"] = datetime.now(timezone.utc).isoformat()
        
        if completed is not None:
            job["completed"] = completed
        
        if success_count is not None:
            job["success_count"] = success_count
        
        if error_count is not None:
            job["error_count"] = error_count
        
        if result:
            job["results"].append(result)
        
        if error_message:
            job["error_message"] = error_message
        
        await r.setex(f"job:{job_id}", 86400, json.dumps(job))
    
    async def increment_progress(
        self,
        job_id: str,
        success: bool,
        result: Optional[Dict] = None
    ):
        """İlerleme sayacını artır"""
        r = await self.get_redis()
        data = await r.get(f"job:{job_id}")
        if not data:
            return
        
        job = json.loads(data)
        job["completed"] = job.get("completed", 0) + 1
        
        if success:
            job["success_count"] = job.get("success_count", 0) + 1
        else:
            job["error_count"] = job.get("error_count", 0) + 1
        
        if result:
            # Son 100 sonucu tut
            results = job.get("results", [])
            results.append(result)
            job["results"] = results[-100:]
        
        await r.setex(f"job:{job_id}", 86400, json.dumps(job))


# Singleton instance
job_service = JobService()

