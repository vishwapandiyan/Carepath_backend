# SQLite to PostgreSQL Migration Plan

**Date**: 2026-08-22  
**Goal**: Consolidate all data into PostgreSQL for production readiness

---

## Current State

### SQLite Database (`app.db`)
- `users` - User authentication
- `patient_ehr` - Patient medical records
- `safety_assessments` - Safety triage history
- `readmission_predictions` - ML predictions
- `post_discharge_statuses` - Post-discharge status (JSON)
- `chat_sessions` - Chat metadata
- `chat_messages` - Chat messages (JSONB)
- `ml_predictions` - General ML predictions
- `notifications` - Patient notifications

### PostgreSQL Database (`carepath_db`)
- `care_plans` - LangGraph care plans
- `care_plan_tasks` - Care plan tasks
- `follow_up_checkins` - Follow-up check-ins

---

## Migration Steps

### Phase 1: Create PostgreSQL Schema ✅

Create all SQLite tables in PostgreSQL with proper types and constraints.

**Files to create:**
- `migrations/001_create_main_schema.sql` - Core tables
- `migrations/002_create_indexes.sql` - Performance indexes
- `migrations/003_create_views.sql` - Helpful views

### Phase 2: Update Database Configuration

**Files to update:**
- `app/db/base.py` - Change from SQLite to PostgreSQL
- `app/db/session.py` - Update connection string
- `app/config.py` - PostgreSQL configuration
- `.env` - Add PostgreSQL credentials

### Phase 3: Data Migration

**Script to create:**
- `migrate_sqlite_to_postgres.py` - Automated migration script

**Process:**
1. Export data from SQLite
2. Transform data (if needed)
3. Import into PostgreSQL
4. Verify data integrity

### Phase 4: Update Application Code

**No changes needed** - SQLAlchemy models will work with both!

### Phase 5: Testing

1. Run backend server with PostgreSQL
2. Test all endpoints
3. Verify data consistency
4. Test care plan generation

---

## Tables to Migrate

| Table | Records | Priority | Notes |
|-------|---------|----------|-------|
| `users` | ~10 | HIGH | Auth required |
| `patient_ehr` | ~10 | HIGH | Core data |
| `readmission_predictions` | ~20 | HIGH | Analytics |
| `safety_assessments` | ~50 | MEDIUM | Historical |
| `post_discharge_statuses` | ~10 | HIGH | Current status |
| `chat_sessions` | ~5 | LOW | Can recreate |
| `chat_messages` | ~50 | LOW | Can recreate |
| `ml_predictions` | ~20 | MEDIUM | Historical |
| `notifications` | ~10 | MEDIUM | Can recreate |

---

## Rollback Plan

1. Keep SQLite database as backup
2. Create PostgreSQL snapshot before migration
3. If issues occur, revert to SQLite configuration
4. Document all changes for easy rollback

---

## Timeline

- **Phase 1**: 15 minutes (Create schema)
- **Phase 2**: 10 minutes (Update config)
- **Phase 3**: 10 minutes (Migrate data)
- **Phase 4**: 0 minutes (No changes needed)
- **Phase 5**: 20 minutes (Testing)

**Total**: ~1 hour

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| Data loss | HIGH | Backup SQLite before migration |
| Connection issues | MEDIUM | Test connection before migration |
| Data type mismatches | LOW | SQLAlchemy handles this |
| Performance issues | LOW | PostgreSQL is faster |

---

## Post-Migration Benefits

✅ Single source of truth  
✅ Better performance  
✅ Proper foreign key relationships  
✅ ACID transactions across all tables  
✅ Production-ready architecture  
✅ Scalability for future growth  
✅ Care plan generation saves correctly  

---

## Next Steps

1. Review this plan
2. Backup current SQLite database
3. Execute Phase 1 (Create schema)
4. Execute Phase 2 (Update config)
5. Execute Phase 3 (Migrate data)
6. Test thoroughly
7. Deploy

**Ready to proceed?**
