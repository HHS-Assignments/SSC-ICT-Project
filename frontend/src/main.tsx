import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type User = {
  id: number;
  email: string;
  name: string;
  role: "user" | "manager" | "admin";
};

type Service = {
  id: number;
  category: string;
  name: string;
  description: string;
  tariff_cents: number | null;
  unit: string;
  delivery_time: string | null;
  unique_name_required: boolean;
  requires_dwo_basis: boolean;
  requires_agreement: boolean;
  requirements: string[];
};

type Order = {
  id: number;
  status: string;
  service_name: string;
  service_category: string;
  service_tariff_cents: number | null;
  user_name: string;
  user_email: string;
  custom_name?: string;
  variant?: string;
  delivery_method?: string;
  justification?: string;
  created_at: string;
};

const USERS = [
  "lotte.devries@example.gov",
  "mira.vandenberg@example.gov",
  "h.vandermeer@example.gov",
  "daan.koster@example.gov",
];

const currency = (cents: number | null) =>
  cents === null ? "Prijs afhankelijk" : new Intl.NumberFormat("nl-NL", { style: "currency", currency: "EUR" }).format(cents / 100);

async function api<T>(path: string, userEmail: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-User-Email": userEmail,
      ...(options.headers || {}),
    },
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || response.statusText);
  }
  return response.json();
}

function App() {
  const [userEmail, setUserEmail] = useState(USERS[0]);
  const [me, setMe] = useState<User | null>(null);
  const [services, setServices] = useState<Service[]>([]);
  const [orders, setOrders] = useState<Order[]>([]);
  const [managerOrders, setManagerOrders] = useState<Order[]>([]);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [selected, setSelected] = useState<Service | null>(null);
  const [customName, setCustomName] = useState("");
  const [variant, setVariant] = useState("");
  const [deliveryMethod, setDeliveryMethod] = useState("office");
  const [agreementAccepted, setAgreementAccepted] = useState(false);
  const [justification, setJustification] = useState("");
  const [message, setMessage] = useState("");

  const categories = useMemo(() => Array.from(new Set(services.map((s) => s.category))).sort(), [services]);

  async function load() {
    setMessage("");
    const [profile, catalog, own] = await Promise.all([
      api<User>("/api/me", userEmail),
      api<Service[]>(`/api/services?q=${encodeURIComponent(query)}&category=${encodeURIComponent(category)}`, userEmail),
      api<Order[]>("/api/orders/my", userEmail),
    ]);
    setMe(profile);
    setServices(catalog);
    setOrders(own);
    if (profile.role === "manager" || profile.role === "admin") {
      setManagerOrders(await api<Order[]>("/api/manager/orders", userEmail));
    } else {
      setManagerOrders([]);
    }
  }

  useEffect(() => {
    load().catch((e) => setMessage(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userEmail, query, category]);

  async function orderService(event: React.FormEvent) {
    event.preventDefault();
    if (!selected) return;
    try {
      const result = await api<Order>("/api/orders", userEmail, {
        method: "POST",
        body: JSON.stringify({
          service_id: selected.id,
          custom_name: customName || null,
          variant: variant || null,
          delivery_method: selected.requires_agreement ? deliveryMethod : null,
          agreement_accepted: agreementAccepted,
          justification: justification || null,
          privacy_notes: null,
        }),
      });
      setMessage(`Aanvraag ${result.id} is aangemaakt met status: ${result.status}.`);
      setCustomName("");
      setVariant("");
      setAgreementAccepted(false);
      setJustification("");
      await load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Aanvraag mislukt");
    }
  }

  async function approve(id: number) {
    await api(`/api/manager/orders/${id}/approve`, userEmail, { method: "POST" });
    await load();
  }

  async function returnOrder(id: number) {
    await api(`/api/orders/${id}/return`, userEmail, { method: "POST" });
    await load();
  }

  return (
    <main id="main" className="layout">
      <header className="hero">
        <div>
          <p className="eyebrow">SSC-ICT Self Service Portal</p>
          <h1>Diensten aanvragen, goedkeuren en teruggeven</h1>
          <p>
            Gebouwd op basis van de factsheet-opdracht met First Time Right-validatie, rolgebaseerde toegang en een toegankelijke interface.
          </p>
        </div>
        <label>
          Demo gebruiker
          <select value={userEmail} onChange={(e) => setUserEmail(e.target.value)} aria-label="Kies demo gebruiker">
            {USERS.map((email) => (
              <option key={email}>{email}</option>
            ))}
          </select>
        </label>
      </header>

      {me && (
        <section aria-label="Ingelogde gebruiker" className="panel">
          <strong>{me.name}</strong> — rol: {me.role}
        </section>
      )}

      {message && (
        <section className="notice" role="status" aria-live="polite">
          {message}
        </section>
      )}

      <section className="filters" aria-label="Catalogus filters">
        <label>
          Zoeken
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Bijv. laptop, Teams, Visio" />
        </label>
        <label>
          Categorie
          <select value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">Alle categorieën</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
      </section>

      <section className="grid" aria-label="Diensten catalogus">
        {services.map((service) => (
          <article key={service.id} className={selected?.id === service.id ? "card selected" : "card"}>
            <span className="tag">{service.category}</span>
            <h2>{service.name}</h2>
            <p>{service.description}</p>
            <dl>
              <dt>Tarief</dt>
              <dd>{currency(service.tariff_cents)}</dd>
              <dt>Eenheid</dt>
              <dd>{service.unit}</dd>
              {service.delivery_time && (
                <>
                  <dt>Levertijd</dt>
                  <dd>{service.delivery_time}</dd>
                </>
              )}
            </dl>
            {service.requirements.length > 0 && (
              <ul>
                {service.requirements.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            )}
            <button type="button" onClick={() => setSelected(service)}>
              Selecteer dienst
            </button>
          </article>
        ))}
      </section>

      {selected && (
        <section className="panel" aria-labelledby="order-heading">
          <h2 id="order-heading">Aanvraagformulier: {selected.name}</h2>
          <form onSubmit={orderService} className="form">
            {selected.unique_name_required && (
              <label>
                Unieke naam
                <input required value={customName} onChange={(e) => setCustomName(e.target.value)} />
              </label>
            )}
            <label>
              Variant of toelichting variant
              <input value={variant} onChange={(e) => setVariant(e.target.value)} placeholder="Bijv. 13 inch, Test, Productie" />
            </label>
            {selected.requires_agreement && (
              <>
                <label>
                  Levering
                  <select value={deliveryMethod} onChange={(e) => setDeliveryMethod(e.target.value)}>
                    <option value="office">Kantoor/balie</option>
                    <option value="home">Thuis</option>
                  </select>
                </label>
                <label className="checkbox">
                  <input type="checkbox" checked={agreementAccepted} onChange={(e) => setAgreementAccepted(e.target.checked)} />
                  Ik accepteer dat uitgifte alleen plaatsvindt na ondertekening van de gebruikersovereenkomst.
                </label>
              </>
            )}
            <label>
              Zakelijke onderbouwing
              <textarea value={justification} onChange={(e) => setJustification(e.target.value)} rows={3} />
            </label>
            <button type="submit">Aanvragen</button>
          </form>
        </section>
      )}

      <section className="panel" aria-labelledby="my-orders">
        <h2 id="my-orders">Mijn geleverde en aangevraagde diensten</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Dienst</th>
                <th>Status</th>
                <th>Naam</th>
                <th>Actie</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
                <tr key={order.id}>
                  <td>{order.service_name}</td>
                  <td>{order.status}</td>
                  <td>{order.custom_name || "—"}</td>
                  <td>
                    {["approved", "delivered"].includes(order.status) && (
                      <button type="button" onClick={() => returnOrder(order.id)}>
                        Teruggeven
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {orders.length === 0 && (
                <tr>
                  <td colSpan={4}>Geen aanvragen gevonden.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {managerOrders.length > 0 && (
        <section className="panel" aria-labelledby="manager-orders">
          <h2 id="manager-orders">Manager overzicht</h2>
          <p>Privacygevoelige notities worden hier niet getoond.</p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Medewerker</th>
                  <th>Dienst</th>
                  <th>Status</th>
                  <th>Actie</th>
                </tr>
              </thead>
              <tbody>
                {managerOrders.map((order) => (
                  <tr key={order.id}>
                    <td>{order.user_name}</td>
                    <td>{order.service_name}</td>
                    <td>{order.status}</td>
                    <td>
                      {order.status === "pending_manager_approval" && (
                        <button type="button" onClick={() => approve(order.id)}>
                          Goedkeuren
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
