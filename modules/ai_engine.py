"""
Module 3 — AI Logic (Groq API Integration)
Uses the groq SDK. Client is lazy-initialized.
"""

import json
import time
import logging
import os
from config import Config

logger = logging.getLogger(__name__)

_client = None

def _get_client():
    global _client
    if _client is None:
        from groq import Groq
        _client = Groq(api_key=Config.GROQ_API_KEY)
    return _client


SYSTEM_PROMPT = (
    "You are an expert ATS analyst and career coach. "
    "Return ONLY a valid JSON object — no markdown fences, no explanations."
)

ANALYSIS_PROMPT_TEMPLATE = """Analyze this resume against the job description. Return ONLY this JSON:

{{
  "ai_match_score": <integer 0-100>,
  "summary": "<2-3 sentence overall assessment>",
  "found_skills": ["<skill>"],
  "missing_skills": ["<skill>"],
  "strengths": ["<point>"],
  "weaknesses": ["<point>"],
  "ats_flags": ["<flag>"]
}}

--- RESUME ---
{resume_text}

--- JOB DESCRIPTION ---
{job_description}
"""

INTERVIEW_PROMPT_TEMPLATE = """You are a world-class interviewer from a top-tier tech company (FAANG-level). 
Generate a comprehensive set of 30 to 35 interview questions and detailed expert answers. 

PRIORITY FOCUS (Area of Interest): {interest}
ADDITIONAL FOCUS (Gaps): {missing_skills}

Structure the questions across these areas:
1. TECHNICAL DEEP-DIVE: Intensive questions on the priority and gap areas.
2. SCENARIO-BASED (Behavioral): Situational questions (leadership, conflict, results).
3. STRATEGIC & CULTURE: General high-level industry prep.

Return ONLY this JSON object:
{{
  "questions": [
    {{
      "category": "Technical | Behavioral | Strategic",
      "question": "The specific interview question...",
      "answer": "A detailed, expert-level sample answer or strategy."
    }}
  ]
}}

Return exactly 30 to 35 high-quality questions. Ensure they are DIFFERENT from standard common ones. Return ONLY JSON.
"""


def _call_groq(prompt: str) -> str:
    client = _get_client()
    last_error = None
    for attempt in range(1, Config.MAX_RETRY + 1):
        try:
            response = client.chat.completions.create(
                model=Config.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=8000, 
            )
            return response.choices[0].message.content
        except Exception as e:
            last_error = e
            logger.warning("Groq attempt %d/%d failed: %s", attempt, Config.MAX_RETRY, e)
            if attempt < Config.MAX_RETRY:
                time.sleep(Config.RETRY_DELAY_SEC)

    raise RuntimeError(f"Groq API failed after {Config.MAX_RETRY} attempts: {last_error}")


def _parse_json(text: str) -> any:
    try:
        # Clean potential markdown fences
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text.strip())
    except Exception as e:
        logger.error("JSON parsing failed: %s\nText: %s", e, text[:200])
        return {}


def _truncate(text: str, max_chars: int) -> str:
    if len(text) > max_chars:
        return text[:max_chars] + "\n\n[...truncated...]"
    return text


def analyze_resume(resume_text: str, job_description: str) -> dict:
    half = Config.MAX_INPUT_CHARS // 2
    prompt = ANALYSIS_PROMPT_TEMPLATE.format(
        resume_text=_truncate(resume_text, half),
        job_description=_truncate(job_description, half),
    )
    raw    = _call_groq(prompt)
    result = _parse_json(raw)

    defaults = {
        "ai_match_score": 0, "summary": "Analysis unavailable.",
        "found_skills": [], "missing_skills": [],
        "strengths": [], "weaknesses": [], "ats_flags": [],
    }
    for key, default in defaults.items():
        result.setdefault(key, default)
    return result


FALLBACK_QUESTIONS = [
    {
        "category": "Technical",
        "question": "How do you ensure high availability and scalability when designing a backend system?",
        "answer": "To ensure high availability and scalability, I use horizontal scaling with load balancers, database clustering/replication (with read/write splitting), caching layers (like Redis), and microservices. I also implement rate limiting, auto-scaling groups, and multi-region deployment to prevent single points of failure."
    },
    {
        "category": "Behavioral",
        "question": "Describe a time you had a technical disagreement with a team member. How did you resolve it?",
        "answer": "In a past project, a colleague wanted to use a NoSQL database while I advocated for a relational database (PostgreSQL) due to complex relational schemas and transaction needs. I scheduled a call to listen to their requirements, built a quick prototype of both options, and compared their trade-offs. Seeing the concrete schema integrity advantages of the relational approach, we agreed to use PostgreSQL."
    },
    {
        "category": "Strategic",
        "question": "How do you keep up-to-date with the latest tech trends and integrate them into your work?",
        "answer": "I follow tech blogs (Netflix Tech Blog, Uber Engineering), read Hacker News, and experiment with new frameworks in side projects. Before proposing any new technology to the production stack, I evaluate its concrete business benefits, support ecosystem, and adoption learning curve rather than just its novelty."
    },
    {
        "category": "Technical",
        "question": "What is your approach to identifying and resolving performance bottlenecks in a web application?",
        "answer": "I use APM tools (e.g., Datadog, New Relic) to profile request latencies. I analyze slow database queries using EXPLAIN ANALYZE, optimize indexes, use Redis to cache expensive/frequent lookups, minimize assets payload, and introduce CDN delivery for static content."
    },
    {
        "category": "Behavioral",
        "question": "Tell me about a time you had to deliver a project under a tight deadline and how you handled the pressure.",
        "answer": "During a critical release, we had to address complex integration bugs. I maintained clear communication with stakeholders about MVP scope priority, deferred non-critical enhancements, organized targeted team pair-programming sessions, and ensured solid test coverage. We shipped the core product on time and with excellent stability."
    },
    {
        "category": "Technical",
        "question": "How do you design and secure RESTful or GraphQL APIs in production?",
        "answer": "I implement OAuth2/JWT for authentication, role-based access control (RBAC) for authorization, HTTPS/TLS for secure transport, rate limiting to prevent DDoS, and CORS policies to control domain access. I also perform thorough input validation, sanitize inputs to prevent injection attacks, and use encrypted environment secrets for sensitive keys."
    },
    {
        "category": "Strategic",
        "question": "How do you approach technical debt in a fast-paced development environment?",
        "answer": "I believe in balancing product delivery with code health. I advocate for allocating around 10-20% of every sprint cycle to refactoring and addressing technical debt. I track code quality metrics, document debt in a shared tracker, and prioritize refactoring of components that are frequently modified or have become bottlenecks for new features."
    },
    {
        "category": "Technical",
        "question": "Explain the differences between SQL and NoSQL databases, and when you would choose one over the other.",
        "answer": "SQL databases are relational, table-based, and enforce strict schemas, making them ideal for complex queries, transactions, and ACID compliance (like financial systems). NoSQL databases (document, key-value, graph) are non-relational, schema-flexible, and scale horizontally effortlessly, making them excellent for unstructured data, real-time analytics, and high-throughput logging."
    },
    {
        "category": "Behavioral",
        "question": "Describe a situation where a project scope suddenly changed. How did you adapt your workflow?",
        "answer": "During a major feature rollout, a critical client requirement changed. I immediately organized a huddle with the product manager, broke down the new requirements into modular sub-tasks, identified which of our completed components could be reused, and adjusted our sprint board to focus on the new MVP requirements. We successfully shipped the updated feature on target without burnout."
    },
    {
        "category": "Strategic",
        "question": "How do you balance product velocity (getting features out fast) with code quality and thorough testing?",
        "answer": "I practice 'pragmatic engineering.' I establish strict automated CI/CD pipelines that enforce unit testing and linting, ensuring a baseline code quality. For critical business paths, I write robust test coverage. For experimental features, I write modular, clean code but may defer extensive E2E tests, ensuring we move fast while maintaining a stable core architecture."
    },
    {
        "category": "Technical",
        "question": "What is a microservices architecture, and how do you handle service-to-service communication and data consistency?",
        "answer": "Microservices break a monolithic app into independent, deployable services. For communication, I use synchronous protocols (gRPC or REST) for direct queries, and asynchronous message brokers (like RabbitMQ or Kafka) for event-driven decoupled systems. To maintain data consistency across services, I implement the Saga pattern or eventual consistency using event sourcing."
    },
    {
        "category": "Behavioral",
        "question": "Tell me about a time you failed to meet a commitment. What did you learn and how did you handle it?",
        "answer": "I once misestimated the integration complexity of a third-party payment system and missed our sprint milestone. As soon as I realized the delay, I flagged it to the PM, explained the technical hurdles, and proposed a partial release strategy (supporting credit cards first, PayPal later). I learned to factor in buffer time for external APIs and always run early feasibility spikes."
    },
    {
        "category": "Strategic",
        "question": "How do you mentor junior developers or team members to level up their skills and engineering practices?",
        "answer": "I hold weekly pair-programming sessions and use code reviews as asynchronous learning opportunities rather than gates. I focus code reviews on explaining the 'why' behind architectural choices. I also encourage junior engineers to own technical tasks start-to-finish, guiding them through system design spikes to build confidence and independence."
    },
    {
        "category": "Technical",
        "question": "How does asymmetric encryption work, and how is it utilized to secure HTTPS connections in modern web traffic?",
        "answer": "Asymmetric encryption uses a mathematically linked pair of keys: a public key for encryption and a private key for decryption. During HTTPS handshakes, the client uses the server's public key (from its SSL certificate) to securely share a randomly generated session key. Once shared, both parties switch to fast symmetric encryption using this shared session key for data transfers."
    },
    {
        "category": "Behavioral",
        "question": "Describe a time you worked on a highly cross-functional project. How did you align different team goals?",
        "answer": "I led the backend migration for a feature where marketing wanted tracking tags, security wanted strict data isolation, and frontend wanted low latency. I set up a joint design spec, documented the constraints openly, and reached a compromise: asynchronous tag loading through a secure backend worker. This kept the UI incredibly fast while fulfilling security and marketing goals."
    },
    {
        "category": "Strategic",
        "question": "What is your philosophy on writing automated tests (Unit, Integration, E2E), and how do you define good test coverage?",
        "answer": "I align with the testing trophy model. Unit tests should cover complex pure functions. Integration tests should ensure business flows (like API request-to-database) work flawlessly, which is where the highest value lies. E2E tests are reserved for the 5-10 critical customer flows. To me, good coverage means testing business logic and boundary failures, rather than chasing 100% line coverage."
    },
    {
        "category": "Technical",
        "question": "What are index structures in relational databases (like B-Trees) and how do they optimize query times?",
        "answer": "A database index is a data structure (commonly a B-Tree or Hash index) that maps a column's values to their physical storage location. Instead of performing a costly sequential table scan (O(N)), the database engine traverses the balanced B-Tree in logarithmic time (O(log N)), rapidly returning matching records and drastically decreasing query latencies."
    },
    {
        "category": "Behavioral",
        "question": "Describe a time you noticed an inefficiency in your team's workflow. What initiative did you take to fix it?",
        "answer": "I noticed our local development environments took hours to set up due to outdated documentation and manual database scripts. I containerized the entire backend and database stack using Docker Compose, wrote shell scripts for automatic database seed loading, and documented the process. This reduced the onboarding and setup time from half a day to a single command."
    },
    {
        "category": "Strategic",
        "question": "How do you decide between building a custom solution in-house versus integrating a third-party SaaS/Open Source library?",
        "answer": "I ask: 'Is this our core competitive advantage?' If yes, we build it custom. If no, I evaluate open-source or SaaS. I weigh development cost, ongoing maintenance, security/compliance, vendor lock-in, and scalability. For instance, we should buy authentication (e.g. Auth0) and search engines (e.g. Algolia) so we can focus on building our core business logic."
    },
    {
        "category": "Technical",
        "question": "How does the Event Loop work in asynchronous runtimes like Node.js or Python's asyncio?",
        "answer": "The Event Loop is a single-threaded execution model that manages asynchronous tasks. When an I/O operation (like a file read or API request) starts, the runtime delegates it to the OS kernel or thread pool and continues executing other code on the call stack. Once the I/O task completes, its callback is queued in the event queue and executed when the call stack becomes empty."
    },
    {
        "category": "Behavioral",
        "question": "Tell me about a time you had to work with extremely vague or incomplete requirements. How did you proceed?",
        "answer": "I was asked to build a 'reporting dashboard' with no specific metrics defined. Instead of guessing, I created wireframes and mock data representing standard metrics. I scheduled a quick demo with key stakeholders to get concrete feedback. This prototype-driven feedback cycle allowed us to nail down the exact requirements and build a highly relevant dashboard."
    },
    {
        "category": "Strategic",
        "question": "What is your approach to designing systems for optimal observability, logging, and application monitoring?",
        "answer": "I design systems with the three pillars of observability: Metrics (for CPU/Memory and HTTP response rates), Structured Logs (using JSON logs with trace/correlation IDs to track requests across microservices), and Distributed Tracing (to analyze network and database bottlenecks). This allows teams to quickly debug issues in production using centralized platforms."
    },
    {
        "category": "Technical",
        "question": "What is the difference between horizontal and vertical scaling, and how does load balancing route traffic?",
        "answer": "Vertical scaling means adding more power (CPU, RAM) to a single server, which is simple but has hard physical and cost limits. Horizontal scaling means adding more server instances to the pool. A load balancer acts as a reverse proxy, distributing incoming HTTP requests using algorithms like Round Robin or Least Connections across these active instances to prevent overloading."
    },
    {
        "category": "Behavioral",
        "question": "Describe a time you had to pitch a new technical architecture to non-technical stakeholders or executives.",
        "answer": "I pitched a rewrite of our legacy checkout flow. Instead of discussing technical terms like microservices, database normalization, or React re-renders, I focused entirely on business impacts. I explained that the new architecture would increase conversion rates by 12%, reduce cloud infrastructure costs by 20%, and speed up feature shipping times from weeks to days."
    },
    {
        "category": "Strategic",
        "question": "How do you evaluate and choose the right tech stack (frameworks, programming languages) for a brand-new product?",
        "answer": "I prioritize team expertise, library ecosystem support, developer speed, and community longevity. I avoid adopting bleeding-edge frameworks with small support networks unless they offer massive, non-trivial competitive advantages. I choose reliable, mature technologies (like React, Python, or Go) to ensure fast hiring and stable production operations."
    },
    {
        "category": "Technical",
        "question": "Explain the concept of containerization (like Docker) and how it differs from traditional Virtual Machines (VMs).",
        "answer": "Virtual Machines bundle a full guest OS, hypervisor, and application binaries, which are resource-heavy and slow to boot. Containers share the host OS kernel and package only the application and its dependencies. This makes containers extremely lightweight (measured in MBs), ultra-portable, and fast to boot, ensuring consistent environment parity across development and production."
    },
    {
        "category": "Behavioral",
        "question": "Describe a conflict you had with a product manager regarding feature feasibility, and how you reached an agreement.",
        "answer": "A PM wanted a real-time recommendation feature that would take weeks to develop. I explained the technical complexity, database load concerns, and potential release delays. We collaborated to find an MVP alternative: a static recommendation block updated nightly via a cron job. This satisfied the user engagement goal, took only a day to build, and kept our release timeline on schedule."
    },
    {
        "category": "Strategic",
        "question": "What is your approach to refactoring legacy code without introducing regressions or breaking production?",
        "answer": "I use the 'Boy Scout Rule'—always leave the code cleaner than you found it. Before editing, I verify there is robust unit and integration test coverage. If tests are missing, I write them first to establish a safety net. I make small, incremental changes, perform thorough local testing, run automated CI checks, and release the changes gradually behind feature flags."
    },
    {
        "category": "Technical",
        "question": "How do database transactions maintain ACID properties, and what are transaction isolation levels?",
        "answer": "ACID guarantees database reliability. Atomic means all operations in a transaction succeed or all fail. Consistency ensures data remains valid. Isolation prevents concurrent transactions from interfering. Durability ensures committed changes survive crashes. Isolation levels (Read Uncommitted, Read Committed, Repeatable Read, Serializable) control the strictness of transaction locking."
    },
    {
        "category": "Behavioral",
        "question": "Tell me about a time you received critical constructive feedback on your code. How did you react and improve?",
        "answer": "In a major pull request, a senior engineer pointed out that my nesting structure made the code hard to read and test. Rather than getting defensive, I thanked them, sat down with them to understand the refactoring approach, and applied a pattern using early returns and flat logic. I documented this pattern for future reference and now incorporate it into all my code."
    },
    {
        "category": "Strategic",
        "question": "How do you approach cloud resource optimization and cost reduction when managing high-scale infrastructure?",
        "answer": "I run regular audits to identify underutilized resources. I configure auto-scaling groups to dynamically spin down instances during off-peak hours. I migrate suitable workloads to serverless or container orchestration platforms, set up lifecycle policies for old data storage (archiving S3 files to Glacier), and use spot or reserved instances for predictable workloads."
    },
    {
        "category": "Technical",
        "question": "What are web sockets, and how do they differ from HTTP polling when designing real-time interactive apps?",
        "answer": "HTTP polling repeatedly sends requests to a server at intervals to check for updates, creating massive overhead and network traffic. WebSockets establish a single, persistent, bi-directional TCP connection between the client and server. This allows real-time, low-overhead, full-duplex communication, making it ideal for chat apps, gaming, and real-time dashboard updates."
    }
]

def generate_interview_questions(missing_skills: list, interest: str = "General") -> list:
    try:
        prompt = INTERVIEW_PROMPT_TEMPLATE.format(
            missing_skills=", ".join(missing_skills) if missing_skills else "Industry standards",
            interest=interest
        )
        raw    = _call_groq(prompt)
        result = _parse_json(raw)
        
        if isinstance(result, dict) and "questions" in result and result["questions"]:
            return result["questions"]
        elif isinstance(result, list) and result:
            return result
    except Exception as e:
        logger.error("Groq interview questions generation failed: %s. Using high-quality fallback questions.", e)
    
    return FALLBACK_QUESTIONS


OPTIMIZE_PROMPT_TEMPLATE = """Based on the analysis, provide specific, professional suggestions to improve this resume for this job. Return ONLY this JSON:
{{
  "professional_summary": "<rewritten professional summary incorporating target keywords>",
  "targeted_improvements": [
    {{"section": "<e.g. Experience, Skills>", "suggestion": "<detailed professional advice>"}}
  ],
  "keyword_injection": ["<list of 5-7 high-impact keywords to add>"]
}}

--- ANALYSIS SUMMARY ---
{summary}

--- MISSING SKILLS ---
{missing_skills}
"""

def generate_resume_optimizations(summary: str, missing_skills: list) -> dict:
    prompt = OPTIMIZE_PROMPT_TEMPLATE.format(
        summary=summary,
        missing_skills=", ".join(missing_skills)
    )
    raw    = _call_groq(prompt)
    result = _parse_json(raw)
    return result if isinstance(result, dict) else {}
