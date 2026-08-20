"""
Chat Export Service
Export chat conversations in various formats (JSON, Text, Markdown)
"""
import json
from datetime import datetime
from typing import List, Dict, Any
from app.db.models import ChatSession, ChatMessage


class ChatExportService:
    """Service class for exporting chat conversations"""
    
    def export_as_json(
        self,
        session: ChatSession,
        messages: List[ChatMessage]
    ) -> str:
        """
        Export chat as JSON format (complete data)
        
        Args:
            session: ChatSession object
            messages: List of ChatMessage objects
        
        Returns:
            str: JSON string
        """
        export_data = {
            "session_id": session.session_id,
            "title": session.title,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "last_message_at": session.last_message_at.isoformat() if session.last_message_at else None,
            "message_count": session.message_count,
            "patient_id": session.patient_id,
            "messages": [
                {
                    "message_id": msg.message_id,
                    "role": msg.role,
                    "content": msg.message_data.get("content", ""),
                    "metadata": msg.message_data.get("metadata", {}),
                    "attachments": msg.message_data.get("attachments", []),
                    "context": msg.message_data.get("context", {}),
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                }
                for msg in messages
            ],
            "exported_at": datetime.utcnow().isoformat()
        }
        
        return json.dumps(export_data, indent=2, ensure_ascii=False)
    
    def export_as_text(
        self,
        session: ChatSession,
        messages: List[ChatMessage]
    ) -> str:
        """
        Export chat as plain text format
        
        Args:
            session: ChatSession object
            messages: List of ChatMessage objects
        
        Returns:
            str: Plain text conversation
        """
        lines = []
        
        # Header
        lines.append("=" * 80)
        lines.append(f"CHAT CONVERSATION: {session.title}")
        lines.append("=" * 80)
        lines.append(f"Session ID: {session.session_id}")
        lines.append(f"Created: {session.created_at.strftime('%Y-%m-%d %H:%M:%S') if session.created_at else 'N/A'}")
        if session.patient_id:
            lines.append(f"Patient ID: {session.patient_id}")
        lines.append(f"Total Messages: {session.message_count}")
        lines.append("=" * 80)
        lines.append("")
        
        # Messages
        for i, msg in enumerate(messages, 1):
            timestamp = msg.created_at.strftime('%Y-%m-%d %H:%M:%S') if msg.created_at else 'N/A'
            role = msg.role.upper()
            content = msg.message_data.get("content", "")
            
            lines.append(f"[{i}] {role} ({timestamp})")
            lines.append("-" * 80)
            lines.append(content)
            lines.append("")
        
        # Footer
        lines.append("=" * 80)
        lines.append(f"Exported: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 80)
        
        return "\n".join(lines)
    
    def export_as_markdown(
        self,
        session: ChatSession,
        messages: List[ChatMessage]
    ) -> str:
        """
        Export chat as Markdown format
        
        Args:
            session: ChatSession object
            messages: List of ChatMessage objects
        
        Returns:
            str: Markdown formatted conversation
        """
        lines = []
        
        # Header
        lines.append(f"# {session.title}")
        lines.append("")
        lines.append(f"**Session ID:** `{session.session_id}`  ")
        lines.append(f"**Created:** {session.created_at.strftime('%B %d, %Y at %I:%M %p') if session.created_at else 'N/A'}  ")
        if session.patient_id:
            lines.append(f"**Patient ID:** `{session.patient_id}`  ")
        lines.append(f"**Total Messages:** {session.message_count}  ")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # Messages
        for i, msg in enumerate(messages, 1):
            timestamp = msg.created_at.strftime('%B %d, %Y at %I:%M %p') if msg.created_at else 'N/A'
            role = msg.role.upper()
            content = msg.message_data.get("content", "")
            
            # Role badge
            if role == "USER":
                role_badge = "👤 **USER**"
            elif role == "ASSISTANT":
                role_badge = "🤖 **ASSISTANT**"
            else:
                role_badge = f"⚙️ **{role}**"
            
            lines.append(f"## Message {i}: {role_badge}")
            lines.append(f"*{timestamp}*")
            lines.append("")
            lines.append(content)
            lines.append("")
            
            # Add metadata if present
            metadata = msg.message_data.get("metadata", {})
            if metadata and role == "ASSISTANT":
                lines.append("<details>")
                lines.append("<summary>Metadata</summary>")
                lines.append("")
                lines.append("```json")
                lines.append(json.dumps(metadata, indent=2))
                lines.append("```")
                lines.append("")
                lines.append("</details>")
                lines.append("")
            
            # Add attachments if present
            attachments = msg.message_data.get("attachments", [])
            if attachments:
                lines.append("**Attachments:**")
                for att in attachments:
                    lines.append(f"- [{att.get('filename', 'Attachment')}]({att.get('url', '#')}) ({att.get('type', 'file')})")
                lines.append("")
            
            lines.append("---")
            lines.append("")
        
        # Footer
        lines.append(f"*Exported: {datetime.utcnow().strftime('%B %d, %Y at %I:%M %p')}*")
        
        return "\n".join(lines)
    
    def export(
        self,
        session: ChatSession,
        messages: List[ChatMessage],
        format: str = "json"
    ) -> str:
        """
        Export chat in specified format
        
        Args:
            session: ChatSession object
            messages: List of ChatMessage objects
            format: Export format ('json', 'txt', 'markdown')
        
        Returns:
            str: Exported content
        """
        format_lower = format.lower()
        
        if format_lower == "json":
            return self.export_as_json(session, messages)
        elif format_lower in ["txt", "text"]:
            return self.export_as_text(session, messages)
        elif format_lower in ["markdown", "md"]:
            return self.export_as_markdown(session, messages)
        else:
            raise ValueError(f"Unsupported export format: {format}")


# Create singleton instance
chat_export_service = ChatExportService()
