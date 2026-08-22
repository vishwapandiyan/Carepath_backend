-- Notifications System for Post-Discharge Care Agent
-- Supports task reminders, appointment alerts, and care manager messages

CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patient_id VARCHAR(50) NOT NULL,
    notification_type VARCHAR(50) NOT NULL CHECK (notification_type IN (
        'task_reminder',
        'appointment_reminder',
        'care_manager_message',
        'task_reframed',
        'followup_scheduled'
    )),
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    
    -- Task-specific fields (nullable for non-task notifications)
    task_index INTEGER,  -- Index of task in care_plan.tasks array
    task_text TEXT,
    
    -- Metadata
    metadata JSONB DEFAULT '{}',
    
    -- Status tracking
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'read', 'dismissed', 'acted_upon')),
    priority VARCHAR(20) DEFAULT 'normal' CHECK (priority IN ('low', 'normal', 'high', 'urgent')),
    
    -- Scheduling
    scheduled_for TIMESTAMP WITH TIME ZONE,
    delivered_at TIMESTAMP WITH TIME ZONE,
    read_at TIMESTAMP WITH TIME ZONE,
    acted_at TIMESTAMP WITH TIME ZONE,
    
    -- Audit
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE  -- Auto-dismiss after this time
);

-- Indexes for performance
CREATE INDEX idx_notifications_patient ON notifications(patient_id);
CREATE INDEX idx_notifications_status ON notifications(status);
CREATE INDEX idx_notifications_type ON notifications(notification_type);
CREATE INDEX idx_notifications_scheduled ON notifications(scheduled_for) WHERE status = 'pending';
CREATE INDEX idx_notifications_pending ON notifications(patient_id, status) WHERE status = 'pending';

-- Update appointment_type column
ALTER TABLE appointments 
ADD COLUMN IF NOT EXISTS appointment_type VARCHAR(50) DEFAULT 'regular'
CHECK (appointment_type IN ('regular', 'post_discharge_followup', 'urgent_followup', 'specialist_referral'));

CREATE INDEX IF NOT EXISTS idx_appointments_type ON appointments(appointment_type);

COMMENT ON TABLE notifications IS 'Patient notification system for care reminders and alerts';
COMMENT ON COLUMN notifications.task_index IS 'Index position of task in post_discharge_statuses.care_plan.tasks array (0-based)';
COMMENT ON COLUMN notifications.scheduled_for IS 'When notification should be delivered (for future scheduling)';
COMMENT ON COLUMN notifications.metadata IS 'Flexible JSON field for notification-specific data (action URLs, etc.)';
