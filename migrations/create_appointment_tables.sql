-- Appointment Agent Database Tables
-- Created: January 2027
-- Purpose: Support alternate care routing and appointment booking

-- ============================================
-- APPOINTMENT SESSION TRACKING
-- ============================================

-- Appointment session tracking (conversation state + workflow)
CREATE TABLE IF NOT EXISTS appointment_sessions (
    session_id VARCHAR(50) PRIMARY KEY,  -- Same as recommendation_id
    mrn VARCHAR(50) NOT NULL,
    destination VARCHAR(50) NOT NULL,  -- PCP, URGENT_CARE, SPECIALIST, TELEHEALTH, DENTISTRY
    specialty VARCHAR(100),
    rule_id VARCHAR(50),
    
    -- Location
    latitude FLOAT,
    longitude FLOAT,
    radius_km FLOAT DEFAULT 15.0,
    source VARCHAR(20) DEFAULT 'PATIENT',  -- PATIENT or CARE_MANAGER
    
    -- Conversation state (full LLM message history as JSONB)
    conversation_state JSONB,
    
    -- Provider candidates from OSM search (JSONB array)
    provider_candidates JSONB,
    
    -- Workflow tracking
    workflow_stage VARCHAR(50) DEFAULT 'NAVIGATION_COMPLETE',
    -- Stages: PROVIDERS_SEARCHED → PROVIDER_SELECTED → AVAILABILITY_CHECKED → SLOT_SELECTED → BOOKED
    
    -- Selected provider
    selected_provider_id VARCHAR(100),
    
    -- Available slots (JSONB array)
    available_slots JSONB,
    
    -- Selected slot
    selected_slot_id VARCHAR(100),
    
    -- Booking result
    appointment_id VARCHAR(50),
    appointment_status VARCHAR(20),  -- BOOKED, CANCELLED, COMPLETED
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP DEFAULT NOW() + INTERVAL '30 minutes'  -- 30-minute TTL
);

CREATE INDEX idx_appointment_sessions_mrn ON appointment_sessions(mrn);
CREATE INDEX idx_appointment_sessions_workflow_stage ON appointment_sessions(workflow_stage);
CREATE INDEX idx_appointment_sessions_created_at ON appointment_sessions(created_at);
CREATE INDEX idx_appointment_sessions_expires_at ON appointment_sessions(expires_at);

COMMENT ON TABLE appointment_sessions IS 'Appointment agent conversation state and workflow tracking';
COMMENT ON COLUMN appointment_sessions.session_id IS 'Same as recommendation_id - single identifier for entire flow';
COMMENT ON COLUMN appointment_sessions.conversation_state IS 'Full LLM message history (JSONB)';
COMMENT ON COLUMN appointment_sessions.provider_candidates IS 'OSM provider search results (JSONB)';
COMMENT ON COLUMN appointment_sessions.expires_at IS '30-minute TTL for recommendation validity';

-- ============================================
-- DEVELOPMENT SCHEDULING BACKEND
-- (Replace with real hospital API in production)
-- ============================================

-- Provider slots (development scheduling)
CREATE TABLE IF NOT EXISTS provider_slots (
    slot_id VARCHAR(50) PRIMARY KEY,
    provider_id VARCHAR(100) NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    status VARCHAR(20) DEFAULT 'AVAILABLE',  -- AVAILABLE, BOOKED
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_provider_slots_provider_id ON provider_slots(provider_id);
CREATE INDEX idx_provider_slots_start_time ON provider_slots(start_time);
CREATE INDEX idx_provider_slots_status ON provider_slots(status);

COMMENT ON TABLE provider_slots IS 'Development scheduling backend - replace with hospital API in production';

-- Appointment bookings
CREATE TABLE IF NOT EXISTS appointments (
    appointment_id VARCHAR(50) PRIMARY KEY,
    mrn VARCHAR(50) NOT NULL,
    provider_id VARCHAR(100) NOT NULL,
    slot_id VARCHAR(50) REFERENCES provider_slots(slot_id),
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP NOT NULL,
    status VARCHAR(20) DEFAULT 'BOOKED',  -- BOOKED, CANCELLED, COMPLETED
    specialty VARCHAR(100),
    destination VARCHAR(50),  -- PCP, URGENT_CARE, etc.
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_appointments_mrn ON appointments(mrn);
CREATE INDEX idx_appointments_status ON appointments(status);
CREATE INDEX idx_appointments_start_time ON appointments(start_time);

COMMENT ON TABLE appointments IS 'Confirmed appointment bookings';

-- Provider directory (development - seeded test data)
CREATE TABLE IF NOT EXISTS appointment_providers (
    provider_id VARCHAR(100) PRIMARY KEY,
    provider_name VARCHAR(255) NOT NULL,
    destination VARCHAR(50),  -- PCP, URGENT_CARE, SPECIALIST, DENTISTRY
    specialty VARCHAR(100),
    address VARCHAR(500),
    latitude FLOAT,
    longitude FLOAT,
    phone VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE appointment_providers IS 'Provider directory - seeded test data for development';

-- ============================================
-- SEED TEST DATA
-- ============================================

-- Seed test providers (Austin, TX area)
INSERT INTO appointment_providers (provider_id, provider_name, destination, address, latitude, longitude, phone) VALUES
('osm:node:test001', 'Austin Urgent Care Center', 'URGENT_CARE', '456 Medical Dr, Austin, TX 78701', 30.2701, -97.7448, '512-555-0101'),
('osm:node:test002', 'Central Texas Family Medicine', 'PCP', '789 Health Plaza, Austin, TX 78701', 30.2680, -97.7440, '512-555-0102'),
('osm:node:test003', 'Austin Orthopedic Specialists', 'SPECIALIST', '321 Bone Rd, Austin, TX 78701', 30.2750, -97.7400, '512-555-0103'),
('osm:node:test004', 'Texas Dental Care', 'DENTISTRY', '555 Smile Ave, Austin, TX 78701', 30.2690, -97.7460, '512-555-0104')
ON CONFLICT (provider_id) DO NOTHING;

-- Seed test slots (next 7 days, 9am-5pm, hourly slots)
-- Only insert if table is empty to avoid duplicates
INSERT INTO provider_slots (slot_id, provider_id, start_time, end_time, status)
SELECT 
    'slot_' || provider_id || '_' || to_char(slot_time, 'YYYYMMDDHH24'),
    provider_id,
    slot_time,
    slot_time + INTERVAL '30 minutes',
    'AVAILABLE'
FROM 
    (SELECT unnest(ARRAY['osm:node:test001', 'osm:node:test002', 'osm:node:test003', 'osm:node:test004']) AS provider_id) providers,
    generate_series(
        NOW() + INTERVAL '1 day',
        NOW() + INTERVAL '7 days',
        INTERVAL '1 hour'
    ) AS slot_time
WHERE EXTRACT(HOUR FROM slot_time) BETWEEN 9 AND 16
  AND NOT EXISTS (SELECT 1 FROM provider_slots LIMIT 1)  -- Only if table is empty
ON CONFLICT (slot_id) DO NOTHING;

-- Verification queries
SELECT 'appointment_sessions' AS table_name, COUNT(*) AS row_count FROM appointment_sessions
UNION ALL
SELECT 'provider_slots', COUNT(*) FROM provider_slots
UNION ALL
SELECT 'appointments', COUNT(*) FROM appointments
UNION ALL
SELECT 'appointment_providers', COUNT(*) FROM appointment_providers;
