-- A real hs-v1 annotation database, dumped verbatim with `sqlite3 .dump`.
--
-- Provenance, because a hand-written fixture would prove nothing: the file this
-- was dumped from was created by the annotation-web binary built from commit
-- fae80cd -- the last revision before session_instrument and item_feedback
-- existed, and the shape production has been running -- driven over HTTP
-- through the real forms. Session 1 is a completed six-item hs-v1 session with
-- labels, evidence quotes and an abstention with a note. Session 2 is a session
-- left in progress, with the original revealed on two items and a third
-- annotation row that has no decision yet.
--
-- Nothing here is edited. In particular the CREATE TABLE statements are the
-- ones persistent-sqlite wrote, IF NOT EXISTS and all, which is exactly what
-- migration 0001 has to be able to recognise on the live file.
PRAGMA foreign_keys=OFF;
BEGIN TRANSACTION;
CREATE TABLE IF NOT EXISTS "survey_session"("id" INTEGER PRIMARY KEY,"presentation_language" VARCHAR NOT NULL,"started_at" TIMESTAMP NOT NULL,"completed_at" TIMESTAMP NULL);
INSERT INTO survey_session VALUES(1,'ru','2026-09-05T18:06:28.921927298Z','2026-09-05T18:06:28.991515382Z');
INSERT INTO survey_session VALUES(2,'en','2026-09-05T18:06:47.909573798Z',NULL);
CREATE TABLE IF NOT EXISTS "annotation"("id" INTEGER PRIMARY KEY,"survey_session_id" INTEGER NOT NULL REFERENCES "survey_session" ON DELETE RESTRICT ON UPDATE RESTRICT,"item_id" VARCHAR NOT NULL,"decision" VARCHAR NULL,"abstention_reason" VARCHAR NULL,"abstention_note" VARCHAR NULL,"original_revealed" BOOLEAN NOT NULL,CONSTRAINT "unique_session_item" UNIQUE ("survey_session_id","item_id"));
INSERT INTO annotation VALUES(1,1,'dg-04','assigned',NULL,NULL,0);
INSERT INTO annotation VALUES(2,1,'dg-05','assigned',NULL,NULL,0);
INSERT INTO annotation VALUES(3,1,'dg-06','none_observed',NULL,NULL,0);
INSERT INTO annotation VALUES(4,1,'dg-07','abstained','insufficient_context','Реплика вырвана из контекста, судить о намерении нельзя',0);
INSERT INTO annotation VALUES(5,1,'dg-08','none_observed',NULL,NULL,0);
INSERT INTO annotation VALUES(6,1,'dg-09','assigned',NULL,NULL,0);
INSERT INTO annotation VALUES(7,2,'dg-04','assigned',NULL,NULL,1);
INSERT INTO annotation VALUES(8,2,'dg-05','assigned',NULL,NULL,1);
INSERT INTO annotation VALUES(9,2,'dg-06',NULL,NULL,NULL,0);
CREATE TABLE IF NOT EXISTS "annotation_label"("id" INTEGER PRIMARY KEY,"annotation_id" INTEGER NOT NULL REFERENCES "annotation" ON DELETE RESTRICT ON UPDATE RESTRICT,"label_id" VARCHAR NOT NULL,CONSTRAINT "unique_annotation_label" UNIQUE ("annotation_id","label_id"));
INSERT INTO annotation_label VALUES(1,1,'B.BLAME_CRITICISM');
INSERT INTO annotation_label VALUES(2,1,'B.PRESSURE_FOR_CHANGE');
INSERT INTO annotation_label VALUES(3,2,'B.BLAME_CRITICISM');
INSERT INTO annotation_label VALUES(4,6,'B.BLAME_CRITICISM');
INSERT INTO annotation_label VALUES(5,7,'B.BLAME_CRITICISM');
INSERT INTO annotation_label VALUES(6,8,'B.BLAME_CRITICISM');
CREATE TABLE IF NOT EXISTS "evidence"("id" INTEGER PRIMARY KEY,"annotation_id" INTEGER NOT NULL REFERENCES "annotation" ON DELETE RESTRICT ON UPDATE RESTRICT,"label_id" VARCHAR NOT NULL,"quote" VARCHAR NOT NULL,CONSTRAINT "unique_evidence" UNIQUE ("annotation_id","label_id"));
INSERT INTO evidence VALUES(1,1,'B.BLAME_CRITICISM','Ты вчера оставил окно открытым, и утром');
INSERT INTO evidence VALUES(2,1,'B.PRESSURE_FOR_CHANGE','Ты вчера оставил окно открытым, и утром');
INSERT INTO evidence VALUES(3,2,'B.BLAME_CRITICISM','Понимаю, почему тебе было страшно. Это правда');
INSERT INTO evidence VALUES(4,6,'B.BLAME_CRITICISM','Я не должна была на тебя орать,');
INSERT INTO evidence VALUES(5,7,'B.BLAME_CRITICISM','You left the window open yesterday, and');
INSERT INTO evidence VALUES(6,8,'B.BLAME_CRITICISM','I understand why you were scared. That');
CREATE TABLE IF NOT EXISTS "audit_event"("id" INTEGER PRIMARY KEY,"survey_session_id" INTEGER NOT NULL REFERENCES "survey_session" ON DELETE RESTRICT ON UPDATE RESTRICT,"item_id" VARCHAR NULL,"kind" VARCHAR NOT NULL,"value" VARCHAR NULL,"occurred_at" TIMESTAMP NOT NULL);
INSERT INTO audit_event VALUES(1,1,NULL,'language_selected','ru','2026-09-05T18:06:28.922953712Z');
INSERT INTO audit_event VALUES(2,1,'dg-04','decision_submitted','assigned','2026-09-05T18:06:28.930020589Z');
INSERT INTO audit_event VALUES(3,1,'dg-04','labels_submitted','B.BLAME_CRITICISM,B.PRESSURE_FOR_CHANGE','2026-09-05T18:06:28.935488169Z');
INSERT INTO audit_event VALUES(4,1,'dg-04','evidence_submitted','B.BLAME_CRITICISM,B.PRESSURE_FOR_CHANGE','2026-09-05T18:06:28.941128404Z');
INSERT INTO audit_event VALUES(5,1,'dg-05','decision_submitted','assigned','2026-09-05T18:06:28.946122892Z');
INSERT INTO audit_event VALUES(6,1,'dg-05','labels_submitted','B.BLAME_CRITICISM','2026-09-05T18:06:28.950342984Z');
INSERT INTO audit_event VALUES(7,1,'dg-05','evidence_submitted','B.BLAME_CRITICISM','2026-09-05T18:06:28.956680153Z');
INSERT INTO audit_event VALUES(8,1,'dg-06','decision_submitted','none_observed','2026-09-05T18:06:28.961252797Z');
INSERT INTO audit_event VALUES(9,1,'dg-07','decision_submitted','abstained','2026-09-05T18:06:28.966284185Z');
INSERT INTO audit_event VALUES(10,1,'dg-07','abstention_submitted','insufficient_context','2026-09-05T18:06:28.97101808Z');
INSERT INTO audit_event VALUES(11,1,'dg-08','decision_submitted','none_observed','2026-09-05T18:06:28.976064314Z');
INSERT INTO audit_event VALUES(12,1,'dg-09','decision_submitted','assigned','2026-09-05T18:06:28.980923811Z');
INSERT INTO audit_event VALUES(13,1,'dg-09','labels_submitted','B.BLAME_CRITICISM','2026-09-05T18:06:28.985085153Z');
INSERT INTO audit_event VALUES(14,1,'dg-09','evidence_submitted','B.BLAME_CRITICISM','2026-09-05T18:06:28.989458565Z');
INSERT INTO audit_event VALUES(15,1,NULL,'session_completed',NULL,'2026-09-05T18:06:28.992109427Z');
INSERT INTO audit_event VALUES(16,2,NULL,'language_selected','en','2026-09-05T18:06:47.910578007Z');
INSERT INTO audit_event VALUES(17,2,'dg-04','original_revealed',NULL,'2026-09-05T18:06:47.915496956Z');
INSERT INTO audit_event VALUES(18,2,'dg-04','decision_submitted','assigned','2026-09-05T18:06:47.919908153Z');
INSERT INTO audit_event VALUES(19,2,'dg-04','labels_submitted','B.BLAME_CRITICISM','2026-09-05T18:06:47.924523368Z');
INSERT INTO audit_event VALUES(20,2,'dg-04','evidence_submitted','B.BLAME_CRITICISM','2026-09-05T18:06:47.929303561Z');
INSERT INTO audit_event VALUES(21,2,'dg-05','original_revealed',NULL,'2026-09-05T18:06:47.934272782Z');
INSERT INTO audit_event VALUES(22,2,'dg-05','decision_submitted','assigned','2026-09-05T18:06:47.938320809Z');
INSERT INTO audit_event VALUES(23,2,'dg-05','labels_submitted','B.BLAME_CRITICISM','2026-09-05T18:06:47.943302655Z');
INSERT INTO audit_event VALUES(24,2,'dg-05','evidence_submitted','B.BLAME_CRITICISM','2026-09-05T18:06:47.947766021Z');
COMMIT;
