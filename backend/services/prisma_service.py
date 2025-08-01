import logging
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import asyncio

logger = logging.getLogger(__name__)

class PrismaService:
    def __init__(self):
        self._is_connected = False
        self._connecting = False
        self._connection_lock = asyncio.Lock()
        self.prisma = None
        try:
            from prisma import Prisma
            self.prisma = Prisma()
            logger.info("Prisma client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Prisma client: {str(e)}")
            raise

    async def connect(self):
        """Connect to the database with proper connection management"""
        async with self._connection_lock:
            if self._is_connected:
                logger.debug("Already connected to database")
                return
            
            if self._connecting:
                logger.debug("Connection already in progress, waiting...")
                while self._connecting:
                    await asyncio.sleep(0.1)
                return
            
            if not self.prisma:
                logger.error("Prisma client not initialized")
                return
            
            self._connecting = True
            try:
                # Check if already connected at Prisma level
                try:
                    # Try a simple query to test connection
                    await self.prisma.calllog.count()
                    self._is_connected = True
                    logger.info("Database connection verified")
                except Exception:
                    # Not connected, proceed with connection
                    if hasattr(self.prisma, 'connect') and callable(self.prisma.connect):
                        import inspect
                        if inspect.iscoroutinefunction(self.prisma.connect):
                            await self.prisma.connect()
                        else:
                            self.prisma.connect()
                        
                        self._is_connected = True
                        logger.info("Connected to Prisma database")
                    else:
                        logger.warning("Prisma client connect method not available")
                        self._is_connected = True
            except Exception as e:
                logger.error(f"Failed to connect to database: {str(e)}")
                # Don't set _is_connected to True if connection actually failed
                self._is_connected = False
            finally:
                self._connecting = False

    async def disconnect(self):
        """Disconnect from the database"""
        async with self._connection_lock:
            if not self._is_connected or not self.prisma:
                return
            
            try:
                if hasattr(self.prisma, 'disconnect') and callable(self.prisma.disconnect):
                    import inspect
                    if inspect.iscoroutinefunction(self.prisma.disconnect):
                        await self.prisma.disconnect()
                    else:
                        self.prisma.disconnect()
                
                self._is_connected = False
                logger.info("Disconnected from Prisma database")
            except Exception as e:
                logger.error(f"Error disconnecting from database: {str(e)}")
                self._is_connected = False

    async def ensure_connected(self):
        """Ensure database connection is active"""
        if not self._is_connected:
            await self.connect()
        
        # Double-check with a test query
        try:
            await self.prisma.calllog.count()
        except Exception as e:
            logger.warning(f"Connection test failed: {str(e)}, attempting reconnect")
            self._is_connected = False
            await self.connect()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    def _check_connection(self):
        """Check if connected to database"""
        if not self.prisma:
            raise Exception("Prisma client not initialized")
        if not self._is_connected:
            raise Exception("Not connected to database")

    # Contact Operations
    async def create_contact(self, name: str, phone: str, email: str = None, company: str = None, notes: str = None):
        """Create a new contact"""
        try:
            await self.ensure_connected()
            contact = await self.prisma.contact.create({
                'data': {
                    'name': name,
                    'phone': phone,
                    'email': email,
                    'company': company,
                    'notes': notes
                }
            })
            logger.info(f"Created contact: {contact.name} ({contact.phone})")
            return contact
        except Exception as e:
            logger.error(f"Error creating contact: {str(e)}")
            raise

    async def get_contact_by_phone(self, phone: str):
        """Get contact by phone number"""
        try:
            await self.ensure_connected()
            contact = await self.prisma.contact.find_unique({
                'where': {'phone': phone}
            })
            return contact
        except Exception as e:
            logger.error(f"Error getting contact by phone: {str(e)}")
            raise

    async def get_all_contacts(self):
        """Get all contacts"""
        try:
            await self.ensure_connected()
            contacts = await self.prisma.contact.find_many({
                'order': {'createdAt': 'desc'}
            })
            return contacts
        except Exception as e:
            logger.error(f"Error getting all contacts: {str(e)}")
            raise

    async def update_contact(self, phone: str, **kwargs):
        """Update contact by phone number"""
        try:
            await self.ensure_connected()
            contact = await self.prisma.contact.update({
                'where': {'phone': phone},
                'data': kwargs
            })
            logger.info(f"Updated contact: {contact.name}")
            return contact
        except Exception as e:
            logger.error(f"Error updating contact: {str(e)}")
            raise

    async def delete_contact(self, phone: str) -> bool:
        """Delete contact by phone number"""
        try:
            await self.ensure_connected()
            contact = await self.prisma.contact.delete({
                'where': {'phone': phone}
            })
            logger.info(f"Deleted contact: {contact.name}")
            return True
        except Exception as e:
            logger.error(f"Error deleting contact: {str(e)}")
            raise

    # Call Log Operations
    async def create_call_log(self, call_sid: str, from_number: str, to_number: str, status: str = "initiated"):
        """Create a new call log entry (no contact dependency)"""
        try:
            await self.ensure_connected()
            call_log = await self.prisma.calllog.create(
                data={
                    'callSid': call_sid,
                    'fromNumber': from_number,
                    'toNumber': to_number,
                    'status': status
                }
            )
            logger.info(f"Created call log: {call_sid}")
            return call_log
        except Exception as e:
            logger.error(f"Error creating call log: {str(e)}")
            raise

    async def update_call_status(self, call_sid: str, status: str, duration: int = None, 
                                error_code: str = None, error_message: str = None, 
                                recording_url: str = None):
        """Update call status and details"""
        try:
            await self.ensure_connected()
            
            # First, try to find the existing call log
            logger.debug(f"Looking for call log with callSid: {call_sid}")
            call_log = await self.prisma.calllog.find_unique(where={'callSid': call_sid})
            
            if not call_log:
                logger.warning(f"Call log not found for {call_sid}. Creating new call log entry.")
                # Create a basic call log entry if it doesn't exist
                call_log = await self.prisma.calllog.create(
                    data={
                        'callSid': call_sid,
                        'fromNumber': 'unknown',  # You might want to pass these as parameters
                        'toNumber': 'unknown',
                        'status': status
                    }
                )
                logger.info(f"Created missing call log for {call_sid}")
            
            # Update the call log
            update_data = {'status': status}
            if duration is not None:
                update_data['duration'] = duration
            if error_code is not None:
                update_data['errorCode'] = error_code
            if error_message is not None:
                update_data['errorMessage'] = error_message
            if recording_url is not None:
                update_data['recordingUrl'] = recording_url
            if status in ['completed', 'failed', 'busy', 'no-answer', 'canceled']:
                update_data['endTime'] = datetime.now()
            
            call_log = await self.prisma.calllog.update(
                where={'callSid': call_sid},
                data=update_data
            )
            logger.info(f"Updated call log {call_sid} status to: {status}")
            return call_log
            
        except Exception as e:
            logger.error(f"Error in update_call_status: {str(e)}")
            return None

    async def get_call_log(self, call_sid: str):
        """Get call log by SID"""
        try:
            await self.ensure_connected()
            call_log = await self.prisma.calllog.find_unique(
                where={'callSid': call_sid},
                include={
                    'contact': True,
                    'session': True,
                    'transcriptions': True
                }
            )
            return call_log
        except Exception as e:
            logger.error(f"Error getting call log: {str(e)}")
            raise

    async def get_all_call_logs(self, limit: int = 100):
        """Get all call logs with pagination"""
        try:
            await self.ensure_connected()
            call_logs = await self.prisma.calllog.find_many(
                take=limit,
                order={'startTime': 'desc'},
                include={
                    'contact': True,
                    'session': True
                }
            )
            return call_logs
        except Exception as e:
            logger.error(f"Error getting all call logs: {str(e)}")
            raise

    # Session Operations
    async def create_session(self, session_id: str, model: str = "gpt-4o-realtime-preview-2024-10-01", 
                           voice: str = "alloy"):
        """Create a new session"""
        try:
            await self.ensure_connected()
            session = await self.prisma.session.create(
                data={
                    'sessionId': session_id,
                    'status': 'created',
                    'model': model,
                    'voice': voice
                }
            )
            logger.info(f"Created session: {session_id}")
            return session
        except Exception as e:
            logger.error(f"Error creating session: {str(e)}")
            raise

    async def update_session_status(self, session_id: str, status: str, duration: int = None):
        """Update session status"""
        try:
            await self.ensure_connected()
            update_data = {'status': status}
            if duration is not None:
                update_data['duration'] = duration
            if status in ['completed', 'failed']:
                update_data['endTime'] = datetime.now()
            session = await self.prisma.session.update(
                where={'sessionId': session_id},
                data=update_data
            )
            logger.info(f"Updated session {session_id} status to: {status}")
            return session
        except Exception as e:
            logger.error(f"Error updating session status: {str(e)}")
            raise

    async def link_session_to_call(self, session_id: str, call_sid: str):
        """Link a session to a call log"""
        try:
            await self.ensure_connected()
            call_log = await self.prisma.calllog.update(
                where={'callSid': call_sid},
                data={'sessionId': session_id}
            )
            logger.info(f"Linked session {session_id} to call {call_sid}")
            return call_log
        except Exception as e:
            logger.error(f"Error linking session to call: {str(e)}")
            raise

    # Transcription Operations
    async def add_transcription(self, call_log_id: int, speaker: str, text: str, 
                               confidence: float = None, session_id: str = None, 
                               is_final: bool = False):
        """Add a transcription entry"""
        try:
            await self.ensure_connected()
            transcription = await self.prisma.transcription.create(
                data={
                    'callLogId': call_log_id,
                    'sessionId': session_id,
                    'speaker': speaker,
                    'text': text,
                    'confidence': confidence,
                    'isFinal': is_final
                }
            )
            logger.debug(f"Added transcription for call {call_log_id}: {speaker} - {text[:50]}...")
            return transcription
        except Exception as e:
            logger.error(f"Error adding transcription: {str(e)}")
            raise

    async def add_transcriptions_batch(self, transcriptions: List[Dict[str, Any]]):
        """Add multiple transcriptions in a batch (robust for SQLite)."""
        if not transcriptions:
            return {'count': 0}
        try:
            await self.ensure_connected()
            saved_count = 0
            for t in transcriptions:
                try:
                    await self.prisma.transcription.create(
                        data={
                            'callLogId': t['call_log_id'],
                            'sessionId': t.get('session_id'),
                            'speaker': t['speaker'],
                            'text': t['text'],
                            'confidence': t.get('confidence'),
                            'isFinal': t.get('is_final', True),
                            'timestamp': t.get('timestamp', datetime.now())
                        }
                    )
                    saved_count += 1
                except Exception as e:
                    logger.warning(f"Failed to save individual transcription: {e}. Data: {t}")
            logger.info(f"Batch processed: Saved {saved_count}/{len(transcriptions)} transcriptions.")
            return {'count': saved_count}
        except Exception as e:
            logger.error(f"Critical error adding transcriptions batch: {str(e)}")
            raise

    async def get_transcriptions_for_call(self, call_log_id: int):
        """Get all transcriptions for a call"""
        try:
            await self.ensure_connected()
            transcriptions = await self.prisma.transcription.find_many(
                where={'callLogId': call_log_id},
                order={'timestamp': 'asc'}
            )
            return transcriptions
        except Exception as e:
            logger.error(f"Error getting transcriptions: {str(e)}")
            raise

    async def get_full_conversation_text(self, call_log_id: int) -> str:
        """Get the full conversation as formatted text"""
        try:
            transcriptions = await self.get_transcriptions_for_call(call_log_id)
            conversation_lines = []
            
            for t in transcriptions:
                speaker_label = "User" if t.speaker == "user" else "Assistant"
                conversation_lines.append(f"{speaker_label}: {t.text}")
            
            return "\n".join(conversation_lines)
        except Exception as e:
            logger.error(f"Error getting full conversation text: {str(e)}")
            return ""

    # Conversation Analysis Operations
    async def create_conversation_analysis(self, call_log_id: int, summary: str = None, 
                                         key_points: List[str] = None, sentiment: str = None,
                                         lead_score: int = None, next_action: str = None):
        """Create conversation analysis"""
        try:
            await self.ensure_connected()
            key_points_json = json.dumps(key_points) if key_points else None
            conversation = await self.prisma.conversation.create(
                data={
                    'callLogId': call_log_id,
                    'summary': summary,
                    'keyPoints': key_points_json,
                    'sentiment': sentiment,
                    'leadScore': lead_score,
                    'nextAction': next_action
                }
            )
            logger.info(f"Created conversation analysis for call {call_log_id}")
            return conversation
        except Exception as e:
            logger.error(f"Error creating conversation analysis: {str(e)}")
            raise

    async def get_conversation_analysis(self, call_log_id: int):
        """Get conversation analysis for a call"""
        try:
            await self.ensure_connected()
            conversation = await self.prisma.conversation.find_unique(
                where={'callLogId': call_log_id}
            )
            return conversation
        except Exception as e:
            logger.error(f"Error getting conversation analysis: {str(e)}")
            raise

    # Utility Methods
    async def get_call_statistics(self) -> Dict[str, Any]:
        """Get call statistics"""
        try:
            await self.ensure_connected()
            total_calls = await self.prisma.calllog.count()
            completed_calls = await self.prisma.calllog.count(where={'status': 'completed'})
            failed_calls = await self.prisma.calllog.count(where={'status': 'failed'})
            return {
                'total_calls': total_calls,
                'completed_calls': completed_calls,
                'failed_calls': failed_calls
            }
        except Exception as e:
            logger.error(f"Error getting call statistics: {str(e)}")
            raise 

    async def upsert_hubspot_temp_data(self, data: Dict[str, Any]):
        """Insert or update a HubspotTempData record by hubspotId"""
        try:
            await self.ensure_connected()
            record = await self.prisma.hubspottempdata.upsert(
                {'hubspotId': data['hubspotId']},
                data={
                    'create': data,
                    'update': data
                },
            )
            return record
        except Exception as e:
            logger.error(f"Error upserting HubspotTempData: {str(e)}")
            raise

    # Additional utility methods for transcription management
    async def get_transcription_summary(self, call_log_id: int) -> Dict[str, Any]:
        """Get summary statistics for transcriptions of a call"""
        try:
            await self.ensure_connected()
            
            total_transcriptions = await self.prisma.transcription.count(
                where={'callLogId': call_log_id}
            )
            
            user_transcriptions = await self.prisma.transcription.count(
                where={'callLogId': call_log_id, 'speaker': 'user'}
            )
            
            assistant_transcriptions = await self.prisma.transcription.count(
                where={'callLogId': call_log_id, 'speaker': 'assistant'}
            )
            
            # Get word counts
            transcriptions = await self.get_transcriptions_for_call(call_log_id)
            total_words = sum(len(t.text.split()) for t in transcriptions)
            user_words = sum(len(t.text.split()) for t in transcriptions if t.speaker == 'user')
            assistant_words = sum(len(t.text.split()) for t in transcriptions if t.speaker == 'assistant')
            
            return {
                'total_transcriptions': total_transcriptions,
                'user_transcriptions': user_transcriptions,
                'assistant_transcriptions': assistant_transcriptions,
                'total_words': total_words,
                'user_words': user_words,
                'assistant_words': assistant_words,
                'conversation_length': len(transcriptions)
            }
        except Exception as e:
            logger.error(f"Error getting transcription summary: {str(e)}")
            return {}

    async def delete_transcriptions_for_call(self, call_log_id: int):
        """Delete all transcriptions for a specific call (useful for cleanup)"""
        try:
            await self.ensure_connected()
            result = await self.prisma.transcription.delete_many(
                where={'callLogId': call_log_id}
            )
            logger.info(f"Deleted {result.count} transcriptions for call {call_log_id}")
            return result.count
        except Exception as e:
            logger.error(f"Error deleting transcriptions for call: {str(e)}")
            raise

    async def get_constant(self, key: str) -> Optional[str]:
        """Retrieve a constant value by key."""
        try:
            await self.ensure_connected()
            constant = await self.prisma.constant.find_unique(
                where={'key': key}
            )
            return constant if constant else None
        except Exception as e:
            logger.error(f"Error getting constant '{key}': {str(e)}")
            return None
        
    async def delete_constant(self, key: str) -> bool:
        """Delete a constant by key."""
        try:
            await self.ensure_connected()
            constant = await self.prisma.constant.delete(
                where={'key': key}
            )
            logger.info(f"Deleted constant '{key}'")
            return True
        except Exception as e:
            logger.error(f"Error deleting constant '{key}': {str(e)}")
            return False
        
    async def set_constant(self, key: str, value: str):
        """Set or update a constant value by key."""
        try:
            await self.ensure_connected()
            constant = await self.prisma.constant.upsert(
                where={
                    'key': key
                },
                data={
                    'create': {
                        'key': key,
                        'value': value
                    },
                    'update': {
                        'value': value
                    }
                }
            )
            logger.info(f"Set constant '{key}'")
            return constant
        except Exception as e:
            logger.error(f"Error setting constant '{key}': {str(e)}")
            raise
    
    async def get_all_constants(self) -> dict:
        """Get all constants as a dict."""
        try:
            await self.ensure_connected()
            constants = await self.prisma.constant.find_many()
            return {c.key: c.value for c in constants}
        except Exception as e:
            logger.error(f"Error getting all constants: {str(e)}")
            return {}

    # Context-aware calling methods
    async def get_previous_calls_for_number(self, phone_number: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Get previous calls for a phone number with their transcriptions"""
        try:
            await self.ensure_connected()
            # Get call logs for this phone number (both to and from)
            call_logs = await self.prisma.calllog.find_many(
                where={
                    "OR": [
                        {"toNumber": phone_number},
                        {"fromNumber": phone_number}
                    ],
                    "status": {"in": ["completed", "answered"]}  # Only successful calls
                },
                include={
                    "transcriptions": True,
                    "conversation": True
                },
                order={"startTime": "desc"},
                take=limit
            )
            
            result = []
            for call in call_logs:
                call_data = {
                    "id": call.id,
                    "callSid": call.callSid,
                    "fromNumber": call.fromNumber,
                    "toNumber": call.toNumber,
                    "status": call.status,
                    "startTime": call.startTime,
                    "endTime": call.endTime,
                    "duration": call.duration,
                    "transcriptions": [],
                    "conversation": None
                }
                
                # Add transcription data
                if call.transcriptions:
                    for trans in call.transcriptions:
                        try:
                            transcript_data = json.loads(trans.transcript) if trans.transcript else []
                            call_data["transcriptions"] = transcript_data
                        except json.JSONDecodeError:
                            logger.warning(f"Invalid JSON in transcription for call {call.callSid}")
                            call_data["transcriptions"] = []
                
                # Add conversation analysis if available
                if call.conversation:
                    call_data["conversation"] = {
                        "summary": call.conversation.summary,
                        "keyPoints": call.conversation.keyPoints,
                        "sentiment": call.conversation.sentiment,
                        "leadScore": call.conversation.leadScore,
                        "nextAction": call.conversation.nextAction
                    }
                
                result.append(call_data)
            
            logger.info(f"Found {len(result)} previous calls for number {phone_number}")
            return result
            
        except Exception as e:
            logger.error(f"Error getting previous calls for number {phone_number}: {str(e)}")
            return []

    async def get_contact_context_by_phone(self, phone_number: str) -> Optional[Dict[str, Any]]:
        """Get contact information and call history context for a phone number"""
        try:
            await self.ensure_connected()
            
            # Try to find existing contact (optional)
            contact = await self.prisma.contact.find_unique(
                where={"phone": phone_number}
            )
            
            # Always get previous calls directly (more reliable)
            previous_calls = await self.get_previous_calls_for_number(phone_number, 3)
            
            return {
                "contact": {
                    "id": contact.id,
                    "name": contact.name,
                    "phone": contact.phone,
                    "email": contact.email,
                    "company": contact.company,
                    "notes": contact.notes
                } if contact else None,
                "call_history": previous_calls
            }
                
        except Exception as e:
            logger.error(f"Error getting contact context for {phone_number}: {str(e)}")
            return None