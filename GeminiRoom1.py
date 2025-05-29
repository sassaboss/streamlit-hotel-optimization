import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# --- Optimizaciona logika izdvojena u zasebnu funkciju i keširana ---
# Privremeno uklanjamo keširanje ili koristimo st.cache_resource za dublje keširanje
# Ako koristite Streamlit verzije pre 1.18, ostavite @st.cache_data
# Ako je novije, @st.cache_resource je bolji za objekte koji se ne menjaju često (kao room_types_data)
# Za ovu svrhu, privremeno ću ukloniti cache_data kako bismo bili sigurni da se uvek izvrši
# @st.cache_data(ttl=3600) # OVO JE SADA ZAKOMENTARISANO
def perform_allocation(total_guests, max_price_per_guest, breakfast_chosen, lunch_chosen, dinner_chosen, room_types_data, available_rooms_data, global_meal_prices_data):

    total_income_from_rooms = 0.0
    total_income_from_meals = 0.0
    total_accommodated_guests = 0
    remaining_guests = total_guests
    allocation = []
    total_rooms_used = 0 # Nova varijabla za praćenje ukupnog broja izdatih soba

    # Izračunavanje cene obroka po gostu za ovu simulaciju
    meal_cost_per_guest_for_all_rooms = 0.0
    if breakfast_chosen:
        meal_cost_per_guest_for_all_rooms += global_meal_prices_data['breakfast']
    if lunch_chosen:
        meal_cost_per_guest_for_all_rooms += global_meal_prices_data['lunch']
    if dinner_chosen:
        meal_cost_per_guest_for_all_rooms += global_meal_prices_data['dinner']

    # Priprema svih soba, sada BEZ POČETNOG FILTRIRANJA po max_price_per_guest
    all_room_types_for_allocation = []
    num_rooms_within_budget = 0 # Broj soba unutar budžeta
    for r in room_types_data:
        temp_room_data = r.copy()
        price_per_guest_room_only = r['price'] / r['capacity'] if r['capacity'] > 0 else float('inf')
        temp_room_data['total_price_per_guest'] = price_per_guest_room_only + meal_cost_per_guest_for_all_rooms

        # Oznaka da li je soba preko maksimalne cene po gostu
        temp_room_data['over_max_budget'] = temp_room_data['total_price_per_guest'] > max_price_per_guest

        if not temp_room_data['over_max_budget']:
            num_rooms_within_budget += 1

        all_room_types_for_allocation.append(temp_room_data)

    if not all_room_types_for_allocation:
        return allocation, total_income_from_rooms, total_income_from_meals, total_accommodated_guests, remaining_guests, "no_rooms_defined", 0.0, 0 # Dodajemo 0 za total_rooms_used

    # Sortiranje soba: prvo po prioritetu, zatim po ceni/kapacitetu, ali sada uključujemo SVE sobe
    room_types_sorted_for_filling = sorted(
        all_room_types_for_allocation,
        key=lambda x: (x['priority'], -(x['price'] / x['capacity'])) # Prioritet i dalje ostaje najvažniji
    )

    current_available_rooms = available_rooms_data.copy()

    for room in room_types_sorted_for_filling:
        if remaining_guests <= 0:
            break

        available_for_allocation = current_available_rooms.get(room['name'], 0)

        if available_for_allocation == 0:
            continue

        num_rooms_to_fill_fully = min(available_for_allocation, remaining_guests // room['capacity'])

        if num_rooms_to_fill_fully > 0:
            guests_in_this_batch = num_rooms_to_fill_fully * room['capacity']

            current_room_income = num_rooms_to_fill_fully * room['price']
            current_meal_income = guests_in_this_batch * meal_cost_per_guest_for_all_rooms # Koristimo preizračunatu cenu obroka

            allocation.append({
                'room_type': room['name'],
                'rooms_used': num_rooms_to_fill_fully,
                'guests_accommodated': guests_in_this_batch,
                'room_income': current_room_income,
                'meal_income': current_meal_income,
                'priority': room['priority'],
                'room_capacity': room['capacity'],
                'total_price_per_guest_for_room': room['total_price_per_guest'], # Dodajemo ukupnu cenu po gostu
                'over_max_budget': room['over_max_budget'] # Dodajemo flag za budžet
            })
            remaining_guests -= guests_in_this_batch
            total_income_from_rooms += current_room_income
            total_income_from_meals += current_meal_income
            total_accommodated_guests += guests_in_this_batch
            total_rooms_used += num_rooms_to_fill_fully # Ažuriranje broja izdatih soba
            current_available_rooms[room['name']] -= num_rooms_to_fill_fully

    # Deo za "ostatke" (jedna soba za preostale goste) - ovde takođe ne filtriramo sobe,
    # ali moramo osigurati da su sobe koje se razmatraju i dalje dostupne
    if remaining_guests > 0:
        room_types_sorted_for_leftovers = sorted(
            [r for r in all_room_types_for_allocation if current_available_rooms.get(r['name'], 0) > 0],
            key=lambda x: (x['priority'], -(x['price'] / x['capacity']))
        )

        for room in room_types_sorted_for_leftovers:
            if remaining_guests <= 0:
                break

            rooms_left_of_this_type = current_available_rooms.get(room['name'], 0)
            if rooms_left_of_this_type > 0:

                guests_to_try_fit = min(remaining_guests, room['capacity'])

                num_rooms_to_use = 1

                current_room_income = num_rooms_to_use * room['price']
                current_meal_income = guests_to_try_fit * meal_cost_per_guest_for_all_rooms

                allocation.append({
                    'room_type': room['name'],
                    'rooms_used': num_rooms_to_use,
                    'guests_accommodated': guests_to_try_fit,
                    'room_income': current_room_income,
                    'meal_income': current_meal_income,
                    'priority': room['priority'],
                    'room_capacity': room['capacity'],
                    'total_price_per_guest_for_room': room['total_price_per_guest'],
                    'over_max_budget': room['over_max_budget']
                })
                remaining_guests -= guests_to_try_fit
                total_income_from_rooms += current_room_income
                total_income_from_meals += current_meal_income
                total_accommodated_guests += guests_to_try_fit
                total_rooms_used += num_rooms_to_use # Ažuriranje broja izdatih soba
                current_available_rooms[room['name']] -= num_rooms_to_use

                if remaining_guests <= 0:
                    break

    # Izračunavanje prosečne ostvarene cene po krevetu (samo smeštaj)
    avg_achieved_price_per_bed_room_only = 0.0
    if total_accommodated_guests > 0:
        avg_achieved_price_per_bed_room_only = total_income_from_rooms / total_accommodated_guests

    # Status poruke se sada odnosi na to da li je BILO KOJA soba unutar budžeta
    status_msg = "success" if remaining_guests == 0 else "partial_success"
    if num_rooms_within_budget == 0 and total_accommodated_guests > 0:
        status_msg = "all_rooms_over_budget" # Posebna poruka ako su sve korišćene sobe preko budžeta
    elif num_rooms_within_budget == 0 and total_accommodated_guests == 0:
        status_msg = "no_rooms_within_budget_and_no_guests" # Nema soba u budžetu i nema smeštenih gostiju

    return allocation, total_income_from_rooms, total_income_from_meals, total_accommodated_guests, remaining_guests, status_msg, avg_achieved_price_per_bed_room_only, total_rooms_used # Dodajemo total_rooms_used u povratnu vrednost

# --- Glavna aplikacija ---
def main():
    st.set_page_config(layout="wide", page_title="Optimizacija Gostiju po Sobama")
    st.markdown("<h1 style='font-size: 48px; color: #0056b3; text-align: center;'>🏨 Optimizacija Rasporeda Gostiju po Sobama</h1>", unsafe_allow_html=True)
    st.markdown("---")

    if 'room_types' not in st.session_state:
        st.session_state.room_types = []
    if 'global_meal_prices' not in st.session_state:
        # --- PODRAZUMEVANE VREDNOSTI ZA OBROKE ---
        st.session_state.global_meal_prices = {'breakfast': 10.0, 'lunch': 15.0, 'dinner': 20.0}

    if not st.session_state.room_types and 'predefined_rooms_added' not in st.session_state:
        # --- NOVI PODACI ZA SOBE PREMA TVOJOJ TABELI ---
        predefined_rooms = [
            {'name': 'junr', 'capacity': 4, 'price': 180.0, 'count': 6, 'priority': 1},
            {'name': 'exec-5', 'capacity': 5, 'price': 200.0, 'count': 1, 'priority': 3},
            {'name': 'exec-6', 'capacity': 6, 'price': 200.0, 'count': 3, 'priority': 3},
            {'name': 'king-2', 'capacity': 2, 'price': 110.0, 'count': 8, 'priority': 2},
            {'name': 'king-4', 'capacity': 4, 'price': 110.0, 'count': 3, 'priority': 2},
            {'name': 'royl-4', 'capacity': 4, 'price': 240.0, 'count': 2, 'priority': 4},
            {'name': 'royl-6', 'capacity': 6, 'price': 240.0, 'count': 2, 'priority': 4},
            {'name': 'twin', 'capacity': 2, 'price': 110.0, 'count': 7, 'priority': 2},
        ]
        st.session_state.room_types.extend(predefined_rooms)
        st.session_state.predefined_rooms_added = True

    for room in st.session_state.room_types:
        if room['name'] not in st.session_state.get('available_rooms', {}):
            if 'available_rooms' not in st.session_state:
                st.session_state.available_rooms = {}
            st.session_state.available_rooms[room['name']] = room['count']

    current_room_names = {room['name'] for room in st.session_state.room_types}
    available_room_names_in_state = list(st.session_state.get('available_rooms', {}).keys())

    for room_name_in_state in available_room_names_in_state:
        if room_name_in_state not in current_room_names:
            del st.session_state.available_rooms[room_name_in_state]


    st.sidebar.header("Kontrole i Podešavanja")
    st.sidebar.markdown("---")

    if st.sidebar.button("Resetuj sve postavke", key="reset_button"):
        st.session_state.clear()
        st.rerun()
    st.sidebar.markdown("---")

    total_guests = st.sidebar.number_input(
        "Ukupan broj gostiju za raspored",
        min_value=1,
        value=30,
        step=1,
        help="Unesite ukupan broj gostiju koje treba rasporediti."
    )

    st.sidebar.subheader("Izbor obroka za raspored")
    col_bf, col_lu, col_di = st.sidebar.columns(3)
    with col_bf:
        breakfast_chosen = st.checkbox("Doručak", value=True)
    with col_lu:
        lunch_chosen = st.checkbox("Ručak", value=False)
    with col_di:
        dinner_chosen = st.checkbox("Večera", value=True)
    st.sidebar.markdown("---")

    st.sidebar.subheader("Kriterijumi rasporeda")
    # *** TEKST AŽURIRAN: Sada je to "ciljna cena" ***
    max_price_per_guest = st.sidebar.number_input(
        "Ciljna maksimalna ukupna cena po gostu (smeštaj + obroci, €)",
        min_value=0.0,
        value=st.session_state.get('max_price_per_guest', 80.0),
        step=5.0,
        help="Ovo je ciljna cena po gostu. Aplikacija će rasporediti goste bez obzira na ovu cenu, ali će naznačiti sobe koje prelaze ovaj budžet."
    )
    st.session_state.max_price_per_guest = max_price_per_guest

    st.sidebar.markdown("---")

    allocation_button = st.sidebar.button("Pokreni Optimizaciju Rasporeda", type="primary", use_container_width=True, key="run_optimization_button")

    st.sidebar.markdown("---")

    tab_available_rooms, tab_meal_settings = st.tabs(["🔢 Trenutno Raspoložive Sobe", "🍽️ Postavke Cena Obroka"])

    with tab_available_rooms:
        st.header("Trenutno Raspoložive Sobe")
        st.write("Ovde možete ručno podesiti broj raspoloživih soba za svaki tip.")

        num_columns = 3
        cols = st.columns(num_columns)

        for i, room in enumerate(st.session_state.room_types):
            with cols[i % num_columns]:
                current_available_for_input = st.session_state.available_rooms.get(room['name'], room['count'])
                if current_available_for_input > room['count']:
                       current_available_for_input = room['count']

                new_available = st.number_input(
                    label=f"**{room['name']}** (ukupno: {room['count']})",
                    min_value=0,
                    max_value=room['count'],
                    value=current_available_for_input,
                    step=1,
                    key=f"available_{room['name']}"
                )
                st.session_state.available_rooms[room['name']] = new_available
        st.markdown("---")

    with tab_meal_settings:
        st.header("Postavke Cena Obroka (Globalne)")
        st.write("Ovde možete podesiti globalne cene za doručak, ručak i večeru. Ove cene se primenjuju na sve goste.")

        with st.form("global_meal_prices_form"):
            new_bf_price = st.number_input("Cena doručka (€)", min_value=0.0, step=1.0,
                                            value=st.session_state.global_meal_prices.get('breakfast', 0.0), key="global_bf_price", format="%.2f")
            new_lunch_price = st.number_input("Cena ručka (€)", min_value=0.0, step=1.0,
                                             value=st.session_state.global_meal_prices.get('lunch', 0.0), key="global_lunch_price", format="%.2f")
            new_dinner_price = st.number_input("Cena večere (€)", min_value=0.0, step=1.0,
                                            value=st.session_state.global_meal_prices.get('dinner', 0.0), key="global_dinner_price", format="%.2f")

            meal_prices_submitted = st.form_submit_button("Sačuvaj globalne cene obroka", type="primary")
            if meal_prices_submitted:
                st.session_state.global_meal_prices['breakfast'] = new_bf_price
                st.session_state.global_meal_prices['lunch'] = new_lunch_price
                st.session_state.global_meal_prices['dinner'] = new_dinner_price
                st.success("Globalne cene obroka su uspešno ažurirane!")
                st.rerun()

    st.markdown("---")

    st.header("🛠️ Upravljanje Tipovima Soba i Prioritetima")
    st.write("Dodajte nove tipove soba ili izmenite/obrišite postojeće.")

    with st.expander("➕ Dodaj novi tip sobe", expanded=False):
        with st.form("add_room_form"):
            col1, col2, col3 = st.columns(3)
            with col1:
                room_name = st.text_input("Naziv tipa sobe", help="Npr. Jednokrevetna, Apartman, Delux", key="add_room_name")
            with col2:
                capacity = st.number_input("Kapacitet (broj gostiju)", min_value=1, step=1, key="add_capacity")
            with col3:
                price = st.number_input("Cena po noćenju (€)", min_value=0.0, step=10.0, key="add_price", format="%.2f")

            col4, col5 = st.columns(2)
            with col4:
                room_count = st.number_input("Ukupan broj soba ovog tipa", min_value=1, step=1, key="add_room_count")
            with col5:
                current_max_priority = max([r['priority'] for r in st.session_state.room_types]) if st.session_state.room_types else 0
                priority = st.number_input("Prioritet (1 = najviši prioritet)", min_value=1, step=1, value=current_max_priority + 1 if current_max_priority > 0 else 1,
                                             help="Sobe sa nižim brojem prioriteta se pune prve.", key="add_priority")

            st.info("Cene obroka za ovaj tip sobe će koristiti globalne postavke.")

            add_submitted = st.form_submit_button("Dodaj tip sobe", type="primary")
            if add_submitted:
                if not room_name:
                    st.error("Naziv tipa sobe ne može biti prazan.")
                elif any(r['name'].lower() == room_name.lower() for r in st.session_state.room_types):
                    st.error(f"Tip sobe '{room_name}' već postoji. Unesite jedinstven naziv.")
                else:
                    new_room = {
                        'name': room_name,
                        'capacity': int(capacity),
                        'price': float(price),
                        'count': int(room_count),
                        'priority': int(priority),
                    }
                    st.session_state.room_types.append(new_room)
                    st.session_state.available_rooms[new_room['name']] = int(room_count)
                    st.success(f"Dodat tip sobe: **{room_name}**")
                    st.rerun()

    st.subheader("Postojeći tipovi soba")
    if not st.session_state.room_types:
        st.info("Trenutno nema dodanih tipova soba.")
    else:
        room_df_display = pd.DataFrame(st.session_state.room_types)
        if not room_df_display.empty:
            room_df_display = room_df_display[['name', 'capacity', 'price', 'count', 'priority']]
            room_df_display.columns = ['Naziv', 'Kapacitet', 'Cena/Noć (€)', 'Ukupno soba', 'Prioritet']

            # Formatiranje kolone 'Cena/Noć (€)' sa dve decimale
            room_df_display['Cena/Noć (€)'] = room_df_display['Cena/Noć (€)'].map('{:.2f}'.format)

            st.dataframe(room_df_display, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("Izmena i brisanje soba")
        st.write("Kliknite na tip sobe ispod da biste ga izmenili ili obbrisali.")

        for i, room in enumerate(st.session_state.room_types[:]):
            with st.expander(f"⚙️ {room['name']} (Kapacitet: {room['capacity']}, Cena: {room['price']}€, Prioritet: {room['priority']})"):
                with st.form(f"edit_room_form_{i}"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        new_name = st.text_input("Naziv", value=room['name'], key=f"edit_name_{i}")
                    with col2:
                        new_cap = st.number_input("Kapacitet", value=room['capacity'], min_value=1, step=1, key=f"edit_cap_{i}")
                    with col3:
                        new_price = st.number_input("Cena po noćenju", value=room['price'], min_value=0.0, step=10.0, key=f"edit_price_{i}", format="%.2f")

                    col4, col5 = st.columns(2)
                    with col4:
                        new_count = st.number_input("Ukupan broj soba", value=room['count'], min_value=1, step=1, key=f"edit_count_{i}")
                    with col5:
                        new_priority = st.number_input("Prioritet", value=room.get('priority', 3), min_value=1, step=1, key=f"edit_priority_{i}")

                    st.info(f"Cene obroka za ovaj tip sobe koriste globalne postavke: Doručak {st.session_state.global_meal_prices['breakfast']:.2f}€, Ručak {st.session_state.global_meal_prices['lunch']:.2f}€, Večera {st.session_state.global_meal_prices['dinner']:.2f}€.")

                    update_submitted = st.form_submit_button("Ažuriraj sobu", type="primary")
                    if update_submitted:
                        if new_name != room['name'] and any(r['name'].lower() == new_name.lower() for j, r in enumerate(st.session_state.room_types) if j != i):
                            st.error(f"Tip sobe '{new_name}' već postoji. Unesite jedinstven naziv.")
                        else:
                            st.session_state.room_types[i] = {
                                'name': new_name,
                                'capacity': int(new_cap),
                                'price': float(new_price),
                                'count': int(new_count),
                                'priority': int(new_priority),
                            }
                            if new_name != room['name']:
                                if room['name'] in st.session_state.available_rooms:
                                    st.session_state.available_rooms[new_name] = st.session_state.available_rooms.pop(room['name'])
                            st.session_state.available_rooms[new_name] = int(new_count)
                            st.success(f"Tip sobe **{new_name}** ažuriran.")
                            st.rerun()

                if st.button(f"🗑️ Obriši {room['name']}", key=f"delete_room_{i}", type="secondary"):
                    original_room_index = -1
                    for idx, r_item in enumerate(st.session_state.room_types):
                        if r_item['name'] == room['name']:
                            original_room_index = idx
                            break

                    if original_room_index != -1:
                        st.session_state.room_types.pop(original_room_index)
                        st.session_state.available_rooms.pop(room['name'], None)
                        st.warning(f"Tip sobe **{room['name']}** obrisan.")
                        st.rerun()
                    else:
                        st.error("Greška pri brisanju sobe: Soba nije pronađena.")

    st.markdown("---")

    st.header("📊 Optimizacija Rasporeda i Izveštaji")

    total_hotel_capacity = sum(room['capacity'] * room['count'] for room in st.session_state.room_types)
    current_available_capacity = 0
    for room_type_data in st.session_state.room_types:
        available_count_for_type = st.session_state.available_rooms.get(room_type_data['name'], 0)
        current_available_capacity += available_count_for_type * room_type_data['capacity']
    total_physical_rooms = sum(room['count'] for room in st.session_state.room_types)


    if allocation_button:
        if not st.session_state.room_types:
            st.error("Nema definisanih tipova soba. Molimo dodajte ih u sekciji 'Upravljanje Tipovima Soba'.")
            st.stop()
        if total_guests <= 0:
            st.error("Broj gostiju mora biti veći od 0.")
            st.stop()

        # Ovdje hvatamo total_rooms_used iz funkcije
        allocation, total_income_from_rooms, total_income_from_meals, total_accommodated_guests, remaining_guests, status_message, avg_achieved_price_per_bed_room_only, total_rooms_used = perform_allocation(
            total_guests, max_price_per_guest, breakfast_chosen, lunch_chosen, dinner_chosen,
            st.session_state.room_types, st.session_state.available_rooms, st.session_state.global_meal_prices
        )

        # DEBUGGING PRINT: Proverite da li se vrednost uopšte generiše
        st.write(f"DEBUG: Vrednost total_rooms_used iz funkcije: {total_rooms_used}")

        # Ažurirane poruke upozorenja
        if status_message == "no_rooms_defined":
            st.error("Nema definisanih tipova soba za raspored. Molimo dodajte ih.")
        elif status_message == "no_rooms_within_budget_and_no_guests":
              st.warning(f"Nijedna soba u hotelu nema ukupnu cenu po gostu manju ili jednaku ciljanoj ({max_price_per_guest:.2f}€). Nije moguće smestiti goste sa datim kriterijumima.")
        elif status_message == "all_rooms_over_budget":
            st.warning(f"Svi gosti su smešteni, ali su sve korišćene sobe prešle ciljanu maksimalnu ukupnu cenu po gostu ({max_price_per_guest:.2f}€). Ipak, pogledajte detaljan raspored ispod.")
        elif remaining_guests > 0:
            st.warning(f"Nije moguće smestiti svih **{total_guests}** gostiju sa datim kriterijumima. Preostalo je **{remaining_guests}** gostiju. Detalji su prikazani ispod.")
        else:
            st.success(f"Svi gosti su uspešno raspoređeni! 🎉")

        total_overall_income = total_income_from_rooms + total_income_from_meals
        avg_price_per_room = total_income_from_rooms / total_rooms_used if total_rooms_used > 0 else 0.0
        avg_price_per_guest = total_overall_income / total_accommodated_guests if total_accommodated_guests > 0 else 0.0


        if allocation:
            st.subheader("Detaljan raspored:")
            df = pd.DataFrame(allocation)
            df['total_income'] = df['room_income'] + df['meal_income']
            df = df.sort_values(by='priority')

            # Dodajemo kolonu za status budžeta
            df['Preko ciljnog budžeta'] = df['over_max_budget'].apply(lambda x: 'Da' if x else 'Ne')

            df_display = df[['room_type', 'rooms_used', 'guests_accommodated', 'room_income', 'meal_income', 'total_income', 'total_price_per_guest_for_room', 'Preko ciljnog budžeta']]
            df_display.columns = ['Tip sobe', 'Broj soba', 'Broj gostiju', 'Prihod od soba (€)', 'Prihod od obroka (€)', 'Ukupan prihod (€)', 'Uk. cena/gost (€)', 'Preko cilj. budžeta']

            # Stilizacija tabele: crvena pozadina za sobe koje prelaze budžet i formatiranje valuta
            def highlight_and_format(row):
                styles = [''] * len(row)
                if row['Preko cilj. budžeta'] == 'Da':
                    styles = ['background-color: #F8D7DA; color: #721C24;'] * len(row)

                # Formatiranje numeričkih kolona
                for i, col in enumerate(df_display.columns):
                    if col in ['Prihod od soba (€)', 'Prihod od obroka (€)', 'Ukupan prihod (€)', 'Uk. cena/gost (€)']:
                        styles[i] += 'text-align: right;' # Poravnanje desno za brojeve
                return styles

            # Definisanje formata za valute
            format_mapping = {
                'Prihod od soba (€)': '{:.2f}',
                'Prihod od obroka (€)': '{:.2f}',
                'Ukupan prihod (€)': '{:.2f}',
                'Uk. cena/gost (€)': '{:.2f}'
            }

            st.dataframe(
                df_display.style.apply(highlight_and_format, axis=1).format(format_mapping),
                use_container_width=True,
                hide_index=True
            )

            st.markdown("---")
            st.subheader("Sumarni pregled ključnih metrika:")

            # --- Kreiranje DataFrame za metrike ---
            metrics_data = {
                "Metrika": [
                    "Ukupan Broj Gostiju (za raspored)",
                    "Ukupan Kapacitet Hotela (kreveta)",
                    "Ukupan Prihod (Sobe)",
                    "Ukupan Prihod (Obroci)",
                    "Ukupan Prihod Hotela",
                    "Prosečna Cena po Gostu (uklj. hranu)",
                    "Prosečna Cena po Zauzetoj Sobi",
                    "Prosečna ostvarena cena po krevetu (samo smeštaj)",
                    "Kapacitet Raspoloživih Kreveta (trenutno)",
                    "Ukupan Broj Smeštenih Gostiju",
                    "Ukupan Broj Fizičkih Soba u Hotelu",
                    "Ukupan Broj Izdatih Soba"
                ],
                "Vrednost": [
                    f"{total_guests}",
                    f"{total_hotel_capacity}",
                    f"{total_income_from_rooms:.2f} €",
                    f"{total_income_from_meals:.2f} €",
                    f"{total_overall_income:.2f} €",
                    f"{avg_price_per_guest:.2f} €",
                    f"{avg_price_per_room:.2f} €",
                    f"{avg_achieved_price_per_bed_room_only:.2f} €",
                    f"{current_available_capacity}",
                    f"{total_accommodated_guests}",
                    f"{total_physical_rooms}",
                    f"{total_rooms_used}"
                ]
            }
            metrics_df = pd.DataFrame(metrics_data)

            # --- Izračunaj dinamičku visinu tabele na osnovu broja redova ---
            # Svaki red je otprilike 35 piksela visok + oko 30 piksela za zaglavlje tabele
            num_metrics = len(metrics_data["Metrika"])
            table_height = (num_metrics * 35) + 50 # Optimalna visina za prikaz svih redova

            # --- Stilizovanje tabele: Zelena za ukupan prihod, svetložuta za prosečnu cenu po zauzetoj sobi ---
            def highlight_kpis(row):
                styles = [''] * len(row)
                if row['Metrika'] == "Ukupan Prihod Hotela":
                    styles = ['background-color: #D4EDDA; font-weight: bold; color: #155724;'] * len(row)
                elif row['Metrika'] == "Prosečna Cena po Zauzetoj Sobi":
                    styles = ['background-color: #FFF3CD;'] * len(row)
                # Dodaj stilizaciju za "Ukupan Broj Izdatih Soba" ako želiš, npr. svetloplava
                elif row['Metrika'] == "Ukupan Broj Izdatih Soba":
                    styles = ['background-color: #E0F2F7; font-weight: bold; color: #0056b3;'] * len(row)
                return styles

            st.dataframe(
                metrics_df.style.apply(highlight_kpis, axis=1),
                use_container_width=True,
                hide_index=True,
                height=table_height # Dodaj ovaj parametar
            )

            st.markdown("---")
            st.subheader("Vizuelni prikaz rezultata:")

            chart_col1, chart_col2 = st.columns(2)

            with chart_col1:
                st.markdown("##### Raspodela smeštenih gostiju po tipu sobe")
                fig_guests_per_room = px.bar(
                    df,
                    x='room_type',
                    y='guests_accommodated',
                    title='Broj gostiju smeštenih po tipu sobe',
                    color='room_type',
                    labels={'room_type': 'Tip sobe', 'guests_accommodated': 'Broj smeštenih gostiju'},
                    height=400
                )
                st.plotly_chart(fig_guests_per_room, use_container_width=True)

            with chart_col2:
                st.markdown("##### Prihod po tipu sobe (smeštaj vs. obroci)")
                df_income_stacked = df[['room_type', 'room_income', 'meal_income']].melt(
                    id_vars='room_type',
                    var_name='Vrsta prihoda',
                    value_name='Prihod (€)'
                )
                df_income_stacked['Vrsta prihoda'] = df_income_stacked['Vrsta prihoda'].map({
                    'room_income': 'Prihod od soba',
                    'meal_income': 'Prihod od obroka'
                })
                fig_income_per_room = px.bar(
                    df_income_stacked,
                    x='room_type',
                    y='Prihod (€)',
                    color='Vrsta prihoda',
                    title='Prihod po tipu sobe (smeštaj vs. obroci)',
                    labels={'room_type': 'Tip sobe', 'Prihod (€)': 'Prihod (€)', 'Vrsta prihoda': 'Vrsta prihoda'},
                    height=400
                )
                st.plotly_chart(fig_income_per_room, use_container_width=True)

            st.markdown("---")
            capacity_col1, capacity_col2 = st.columns(2)

            with capacity_col1:
                st.markdown("##### Iskorišćenost kapaciteta hotela - brzi pregled")

                percentage_occupied = (total_accommodated_guests / total_hotel_capacity * 100) if total_hotel_capacity > 0 else 0

                fig_gauge = go.Figure(go.Indicator(
                    mode = "gauge+number",
                    value = percentage_occupied,
                    domain = {'x': [0, 1], 'y': [0, 1]},
                    title = {'text': "Procenat popunjenosti hotela", 'font': {'size': 18}},
                    gauge = {
                        'axis': {'range': [None, 100], 'tickwidth': 1, 'tickcolor': "darkblue"},
                        'bar': {'color': "#17A2B8"},
                        'bgcolor': "white",
                        'borderwidth': 2,
                        'bordercolor': "gray",
                        'steps': [
                            {'range': [0, 50], 'color': "#FFC107"},
                            {'range': [50, 80], 'color': "#28A745"},
                            {'range': [80, 100], 'color': "#007BFF"}
                        ],
                        'threshold': {
                            'line': {'color': "red", 'width': 4},
                            'thickness': 0.75,
                            'value': 90
                        }}
                ))
                fig_gauge.update_layout(height=300)
                st.plotly_chart(fig_gauge, use_container_width=True)

            with capacity_col2:
                st.markdown("##### Detaljan pregled kapaciteta i popunjenosti kreveta")
                capacity_data = pd.DataFrame({
                    'Kategorija': ['Ukupan Kapacitet Kreveta', 'Trenutno Raspoloživi Kreveti', 'Smešteni Gosti'],
                    'Broj Kreveta': [total_hotel_capacity, current_available_capacity, total_accommodated_guests]
                })
                fig_capacity_bar = px.bar(
                    capacity_data,
                    x='Kategorija',
                    y='Broj Kreveta',
                    title='Kapacitet i popunjenost kreveta',
                    color='Kategorija',
                    labels={'Kategorija': 'Kategorija kapaciteta', 'Broj Kreveta': 'Broj kreveta'},
                    height=400
                )
                st.plotly_chart(fig_capacity_bar, use_container_width=True)

        else:
            st.info("Nema alokacije za zadate parametre. Nije moguće smestiti goste. Proverite raspoložive sobe i broj gostiju.")

    else:
        st.info("Unesite broj gostiju (u sidebaru), podesite kriterijume i kliknite 'Pokreni Optimizaciju Rasporeda' (u sidebaru).")


if __name__ == '__main__':
    main()