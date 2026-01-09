# -*- coding: utf-8 -*-
"""
Session Management Service
- Aktif oturumların yönetimi
- Cihaz bilgisi çıkarma
- Oturum sonlandırma
"""

import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, and_, desc
from user_agents import parse as parse_user_agent

from app.models.session import UserSession
from app.core.config import settings

security_logger = logging.getLogger("security")


class SessionService:
    """Session management servisi"""
    
    @staticmethod
    def hash_token(token: str) -> str:
        """Token'ı hashle (güvenli saklama için)"""
        return hashlib.sha256(token.encode()).hexdigest()
    
    @staticmethod
    def parse_device_info(user_agent_string: str) -> Dict[str, str]:
        """User-Agent'dan cihaz bilgilerini çıkar"""
        try:
            ua = parse_user_agent(user_agent_string)
            
            # Cihaz tipi
            if ua.is_mobile:
                device_type = "mobile"
            elif ua.is_tablet:
                device_type = "tablet"
            else:
                device_type = "desktop"
            
            # Cihaz adı
            browser = f"{ua.browser.family} {ua.browser.version_string}"
            os_info = f"{ua.os.family} {ua.os.version_string}"
            device_name = f"{browser} on {os_info}"
            
            return {
                "device_name": device_name,
                "device_type": device_type,
                "browser": ua.browser.family,
                "os": ua.os.family,
            }
        except Exception:
            return {
                "device_name": "Bilinmeyen Cihaz",
                "device_type": "unknown",
                "browser": "Unknown",
                "os": "Unknown",
            }
    
    @staticmethod
    async def create_session(
        db: AsyncSession,
        user_id: int,
        company_id: int,
        refresh_token: str,
        ip_address: str,
        user_agent: str,
        location: Optional[str] = None,
    ) -> UserSession:
        """
        Yeni oturum oluştur
        
        Args:
            db: Database session
            user_id: Kullanıcı ID
            company_id: Şirket ID
            refresh_token: Refresh token
            ip_address: İstemci IP adresi
            user_agent: Tarayıcı bilgisi
            location: Konum bilgisi (opsiyonel)
        
        Returns:
            Oluşturulan UserSession
        """
        # Cihaz bilgilerini çıkar
        device_info = SessionService.parse_device_info(user_agent)
        
        # Token hash'le
        token_hash = SessionService.hash_token(refresh_token)
        
        # Expire time hesapla
        expires_at = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        
        session = UserSession(
            user_id=user_id,
            company_id=company_id,
            session_token=token_hash,
            device_name=device_info["device_name"],
            device_type=device_info["device_type"],
            browser=device_info["browser"],
            os=device_info["os"],
            ip_address=ip_address,
            location=location,
            is_active=True,
            is_current=True,
            expires_at=expires_at,
        )
        
        # Diğer oturumların is_current'ını false yap
        await db.execute(
            update(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.is_current == True
            )
            .values(is_current=False)
        )
        
        db.add(session)
        
        security_logger.info(
            f"SESSION_CREATE | User: {user_id} | Device: {device_info['device_name']} | IP: {ip_address}"
        )
        
        return session
    
    @staticmethod
    async def update_activity(
        db: AsyncSession,
        refresh_token: str,
    ) -> Optional[UserSession]:
        """Oturum aktivitesini güncelle"""
        token_hash = SessionService.hash_token(refresh_token)
        
        result = await db.execute(
            select(UserSession).where(
                UserSession.session_token == token_hash,
                UserSession.is_active == True
            )
        )
        session = result.scalar_one_or_none()
        
        if session:
            session.last_activity = datetime.utcnow()
            session.is_current = True
            
            # Diğer oturumların is_current'ını false yap
            await db.execute(
                update(UserSession)
                .where(
                    UserSession.user_id == session.user_id,
                    UserSession.id != session.id,
                    UserSession.is_current == True
                )
                .values(is_current=False)
            )
        
        return session
    
    @staticmethod
    async def get_user_sessions(
        db: AsyncSession,
        user_id: int,
        include_expired: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Kullanıcının tüm oturumlarını getir
        
        Args:
            db: Database session
            user_id: Kullanıcı ID
            include_expired: Süresi dolmuş oturumları dahil et
        
        Returns:
            Oturum listesi
        """
        query = select(UserSession).where(UserSession.user_id == user_id)
        
        if not include_expired:
            query = query.where(UserSession.is_active == True)
        
        query = query.order_by(desc(UserSession.last_activity))
        
        result = await db.execute(query)
        sessions = result.scalars().all()
        
        return [
            {
                "id": s.id,
                "device_name": s.device_name,
                "device_type": s.device_type,
                "browser": s.browser,
                "os": s.os,
                "ip_address": s.ip_address,
                "location": s.location,
                "is_active": s.is_active,
                "is_current": s.is_current,
                "is_expired": s.is_expired,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "last_activity": s.last_activity.isoformat() if s.last_activity else None,
                "expires_at": s.expires_at.isoformat() if s.expires_at else None,
            }
            for s in sessions
        ]
    
    @staticmethod
    async def terminate_session(
        db: AsyncSession,
        session_id: int,
        user_id: int,
    ) -> bool:
        """
        Belirli bir oturumu sonlandır
        
        Args:
            db: Database session
            session_id: Sonlandırılacak oturum ID
            user_id: Oturum sahibi kullanıcı ID (güvenlik için)
        
        Returns:
            Başarılı mı
        """
        result = await db.execute(
            select(UserSession).where(
                UserSession.id == session_id,
                UserSession.user_id == user_id
            )
        )
        session = result.scalar_one_or_none()
        
        if not session:
            return False
        
        session.is_active = False
        session.terminated_at = datetime.utcnow()
        
        security_logger.warning(
            f"SESSION_TERMINATE | User: {user_id} | Session: {session_id} | Device: {session.device_name}"
        )
        
        return True
    
    @staticmethod
    async def terminate_all_sessions(
        db: AsyncSession,
        user_id: int,
        except_current: bool = True,
        current_token: Optional[str] = None,
    ) -> int:
        """
        Tüm oturumları sonlandır
        
        Args:
            db: Database session
            user_id: Kullanıcı ID
            except_current: Mevcut oturumu hariç tut
            current_token: Mevcut oturumun token'ı
        
        Returns:
            Sonlandırılan oturum sayısı
        """
        query = (
            update(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.is_active == True
            )
            .values(is_active=False, terminated_at=datetime.utcnow())
        )
        
        # Mevcut oturumu hariç tut
        if except_current and current_token:
            token_hash = SessionService.hash_token(current_token)
            query = query.where(UserSession.session_token != token_hash)
        
        result = await db.execute(query)
        count = result.rowcount
        
        security_logger.warning(
            f"SESSION_TERMINATE_ALL | User: {user_id} | Count: {count}"
        )
        
        return count
    
    @staticmethod
    async def terminate_session_by_token(
        db: AsyncSession,
        refresh_token: str,
    ) -> bool:
        """Token ile oturumu sonlandır (logout için)"""
        token_hash = SessionService.hash_token(refresh_token)
        
        result = await db.execute(
            update(UserSession)
            .where(UserSession.session_token == token_hash)
            .values(is_active=False, terminated_at=datetime.utcnow())
        )
        
        return result.rowcount > 0
    
    @staticmethod
    async def cleanup_expired_sessions(
        db: AsyncSession,
        days_old: int = 30,
    ) -> int:
        """Eski oturumları temizle"""
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        
        result = await db.execute(
            delete(UserSession).where(
                UserSession.expires_at < cutoff_date
            )
        )
        
        return result.rowcount
    
    @staticmethod
    async def get_active_session_count(
        db: AsyncSession,
        user_id: int,
    ) -> int:
        """Aktif oturum sayısını getir"""
        result = await db.execute(
            select(func.count(UserSession.id)).where(
                UserSession.user_id == user_id,
                UserSession.is_active == True
            )
        )
        return result.scalar() or 0


# Singleton instance
session_service = SessionService()

