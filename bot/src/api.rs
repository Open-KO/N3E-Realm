//! The two HTTP services the bot calls: the realm's admin API (spec 03) and GitHub's
//! `workflow_dispatch` for `/deploy`. Neither is retried (spec 05 "Fail fast").

use serde_json::Value;
use std::time::Duration;

/// How long an admin call may take before the bot says the realm is unavailable.
pub const ADMIN_TIMEOUT: Duration = Duration::from_secs(5);

/// What an admin API call came to, in the terms the bot replies in.
#[derive(Debug, Clone, PartialEq)]
pub enum Outcome {
    /// 2xx; `Value::Null` for an empty body.
    Ok(u16, Value),
    /// 4xx other than 401: the API's `error` and `detail`.
    Refused(u16, String, Option<String>),
    /// 401: the bot's token is unknown or revoked.
    Rejected,
    /// 501: the route's milestone has not landed on this realm.
    NotImplemented,
    /// Could not connect, timed out, or 5xx.
    Unavailable,
}

pub struct Admin {
    http: reqwest::Client,
    base: String,
    token: String,
}

impl Admin {
    pub fn new(base: &str, token: &str) -> Self {
        Self {
            http: reqwest::Client::builder()
                .timeout(ADMIN_TIMEOUT)
                .connect_timeout(ADMIN_TIMEOUT)
                .build()
                .expect("an HTTP client with timeouts"),
            base: base.to_string(),
            token: token.to_string(),
        }
    }

    pub async fn get(&self, path: &str) -> Outcome {
        self.call(reqwest::Method::GET, path, None).await
    }

    pub async fn post(&self, path: &str, body: Value) -> Outcome {
        self.call(reqwest::Method::POST, path, Some(body)).await
    }

    pub async fn put(&self, path: &str, body: Value) -> Outcome {
        self.call(reqwest::Method::PUT, path, Some(body)).await
    }

    async fn call(&self, method: reqwest::Method, path: &str, body: Option<Value>) -> Outcome {
        let mut request = self
            .http
            .request(method, format!("{}{path}", self.base))
            .bearer_auth(&self.token);
        if let Some(body) = body {
            request = request.json(&body);
        }
        let Ok(response) = request.send().await else {
            return Outcome::Unavailable;
        };
        let status = response.status().as_u16();
        let Ok(bytes) = response.bytes().await else {
            return Outcome::Unavailable;
        };
        let value = if bytes.is_empty() {
            Value::Null
        } else {
            serde_json::from_slice(&bytes).unwrap_or(Value::Null)
        };
        match status {
            200..=299 => Outcome::Ok(status, value),
            401 => Outcome::Rejected,
            501 => Outcome::NotImplemented,
            400..=499 => Outcome::Refused(
                status,
                value["error"].as_str().unwrap_or("error").to_string(),
                value["detail"].as_str().map(str::to_string),
            ),
            _ => Outcome::Unavailable,
        }
    }
}

/// `POST /repos/{repo}/actions/workflows/{wf}/dispatches`, then the run it started.
pub struct GitHub {
    http: reqwest::Client,
    config: crate::config::GitHub,
}

impl GitHub {
    pub fn new(config: crate::config::GitHub) -> Self {
        Self {
            http: reqwest::Client::builder()
                .timeout(Duration::from_secs(10))
                .user_agent(concat!("realm-bot/", env!("CARGO_PKG_VERSION")))
                .build()
                .expect("an HTTP client with timeouts"),
            config,
        }
    }

    fn request(&self, method: reqwest::Method, path: &str) -> reqwest::RequestBuilder {
        self.http
            .request(
                method,
                format!(
                    "{}/repos/{}/actions/workflows/{}{path}",
                    self.config.api, self.config.repo, self.config.workflow
                ),
            )
            .bearer_auth(&self.config.token)
            .header("Accept", "application/vnd.github+json")
            .header("X-GitHub-Api-Version", "2022-11-28")
    }

    /// Dispatches the CD workflow on `master` with `force: "true"`. `Err` is the text to
    /// show the operator: GitHub's own message for a 4xx (spec 05 "Failure modes").
    pub async fn dispatch(&self, reason: &str) -> Result<(), String> {
        let body =
            serde_json::json!({"ref": "master", "inputs": {"force": "true", "reason": reason}});
        let response = self
            .request(reqwest::Method::POST, "/dispatches")
            .json(&body)
            .send()
            .await
            .map_err(|_| "GitHub did not answer".to_string())?;
        let status = response.status();
        if status.is_success() {
            return Ok(());
        }
        let text = response.text().await.unwrap_or_default();
        let message = serde_json::from_str::<Value>(&text)
            .ok()
            .and_then(|v| v["message"].as_str().map(str::to_string))
            .unwrap_or(text);
        Err(format!(
            "GitHub refused the dispatch ({}): {}",
            status.as_u16(),
            crate::text::escape(message.chars().take(300).collect::<String>().as_str())
        ))
    }

    /// The newest `workflow_dispatch` run created at or after `since` (RFC 3339), polled
    /// for at most 30 s.
    pub async fn run_after(&self, since: &str) -> Option<String> {
        let deadline = tokio::time::Instant::now() + Duration::from_secs(30);
        loop {
            if let Ok(response) = self
                .request(
                    reqwest::Method::GET,
                    "/runs?event=workflow_dispatch&per_page=5",
                )
                .send()
                .await
            {
                if let Ok(v) = response.json::<Value>().await {
                    let found = v["workflow_runs"].as_array().and_then(|runs| {
                        runs.iter()
                            .filter(|r| r["created_at"].as_str().is_some_and(|c| c >= since))
                            .find_map(|r| r["html_url"].as_str().map(str::to_string))
                    });
                    if found.is_some() {
                        return found;
                    }
                }
            }
            if tokio::time::Instant::now() + Duration::from_secs(3) > deadline {
                return None;
            }
            tokio::time::sleep(Duration::from_secs(3)).await;
        }
    }
}
