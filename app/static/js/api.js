// API helper module for E-Eye client
export async function getJson(url) {
  try {
    const res = await fetch(url, {
      headers: { "Accept": "application/json" }
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    }
    return await res.json();
  } catch (err) {
    console.error("API GET failed:", url, err);
    throw err;
  }
}

export async function postJson(url, data = {}) {
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Accept": "application/json"
      },
      body: JSON.stringify(data)
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    }
    return await res.json();
  } catch (err) {
    console.error("API POST failed:", url, err);
    throw err;
  }
}

export async function deleteJson(url) {
  try {
    const res = await fetch(url, {
      method: "DELETE",
      headers: { "Accept": "application/json" }
    });
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    }
    return await res.json();
  } catch (err) {
    console.error("API DELETE failed:", url, err);
    throw err;
  }
}
