--
-- PostgreSQL database dump
--

\restrict X3g2KMcMblEX3K3DkF1CDPZ5hVJIDGTvLUwgfou1xLhavnUBJgYv2QFeFId4Rd9

-- Dumped from database version 16.15 (Debian 16.15-1.pgdg13+2)
-- Dumped by pg_dump version 16.15 (Debian 16.15-1.pgdg13+2)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: flyway_schema_history; Type: TABLE; Schema: public; Owner: notification
--

CREATE TABLE public.flyway_schema_history (
    installed_rank integer NOT NULL,
    version character varying(50),
    description character varying(200) NOT NULL,
    type character varying(20) NOT NULL,
    script character varying(1000) NOT NULL,
    checksum integer,
    installed_by character varying(100) NOT NULL,
    installed_on timestamp without time zone DEFAULT now() NOT NULL,
    execution_time integer NOT NULL,
    success boolean NOT NULL
);


ALTER TABLE public.flyway_schema_history OWNER TO notification;

--
-- Name: sent_email; Type: TABLE; Schema: public; Owner: notification
--

CREATE TABLE public.sent_email (
    id uuid NOT NULL,
    source_event_id text NOT NULL,
    event_type text NOT NULL,
    reason text,
    recipient_type text NOT NULL,
    recipient_key text NOT NULL,
    customer_id text,
    order_id text,
    subject text NOT NULL,
    body text NOT NULL,
    status text NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    sent_at timestamp with time zone,
    failed_at timestamp with time zone,
    error text,
    recipient_email text,
    CONSTRAINT sent_email_recipient_type_check CHECK ((recipient_type = ANY (ARRAY['customer'::text, 'email'::text, 'order'::text]))),
    CONSTRAINT sent_email_status_check CHECK ((status = ANY (ARRAY['pending'::text, 'sent'::text, 'failed'::text, 'unresolved'::text])))
);


ALTER TABLE public.sent_email OWNER TO notification;

--
-- Name: flyway_schema_history flyway_schema_history_pk; Type: CONSTRAINT; Schema: public; Owner: notification
--

ALTER TABLE ONLY public.flyway_schema_history
    ADD CONSTRAINT flyway_schema_history_pk PRIMARY KEY (installed_rank);


--
-- Name: sent_email sent_email_pkey; Type: CONSTRAINT; Schema: public; Owner: notification
--

ALTER TABLE ONLY public.sent_email
    ADD CONSTRAINT sent_email_pkey PRIMARY KEY (id);


--
-- Name: sent_email sent_email_source_event_id_key; Type: CONSTRAINT; Schema: public; Owner: notification
--

ALTER TABLE ONLY public.sent_email
    ADD CONSTRAINT sent_email_source_event_id_key UNIQUE (source_event_id);


--
-- Name: flyway_schema_history_s_idx; Type: INDEX; Schema: public; Owner: notification
--

CREATE INDEX flyway_schema_history_s_idx ON public.flyway_schema_history USING btree (success);


--
-- Name: sent_email_customer_id_created_at_idx; Type: INDEX; Schema: public; Owner: notification
--

CREATE INDEX sent_email_customer_id_created_at_idx ON public.sent_email USING btree (customer_id, created_at DESC);


--
-- Name: sent_email_order_id_created_at_idx; Type: INDEX; Schema: public; Owner: notification
--

CREATE INDEX sent_email_order_id_created_at_idx ON public.sent_email USING btree (order_id, created_at DESC);


--
-- PostgreSQL database dump complete
--

\unrestrict X3g2KMcMblEX3K3DkF1CDPZ5hVJIDGTvLUwgfou1xLhavnUBJgYv2QFeFId4Rd9

