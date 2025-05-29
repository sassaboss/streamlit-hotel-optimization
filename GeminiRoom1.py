import streamlit as st
import pandas as pd
import uuid

# Funkcija za stilizovanje sumarnog pregleda
def style_summary_table(row, num_days):
    styles = [''] * len(row)
    # Prilagođeno da se poklapa sa nazivima metrika koje su vraćene
    if row['Metrika'] == f"Ukupan Prihod Hotela (za {num_days} dana)":
        styles[1] = 'background-color: #e6ffe6' # Svetlo zelena
    elif row['Metrika'] == "Prosečna cena po zauzetoj sobi":
        styles[1] = 'background-color: #fff8e6' # Svetlo žuta
    return styles

# Funkcija za stilizovanje redova u tabeli alokacije
def highlight_over_budget(row):
    # Proverava status "DA" za prebojavanje
    if row['Soba iznad budžeta (po gostu)'] == "DA":
        return ['background-color: #ffe0e0'] * len(row) # Svetlo crvena pozadina
    return [''] * len(row)

def perform_allocation(total_guests, guests_willing_to_share, max_price_per_guest, breakfast_chosen, lunch_chosen, dinner_chosen, individual_rooms_data, global_meal_prices_data, num_days):
    total_income_from_rooms = 0.0
    total_income_from_meals = 0.0
    total_accommodated_guests = 0
    remaining_guests = total_guests
    remaining_guests_willing_to_share = guests_willing_to_share
    allocation = []
    total_rooms_used_count = 0

    # Izračunavanje cene obroka po gostu
    meal_cost_per_guest_for_all_rooms = 0.0
    if breakfast_chosen:
        meal_cost_per_guest_for_all_rooms += global_meal_prices_data['breakfast']
    if lunch_chosen:
        meal_cost_per_guest_for_all_rooms += global_meal_prices_data['lunch']
    if dinner_chosen:
        meal_cost_per_guest_for_all_rooms += global_meal_prices_data['dinner']

    # Filtrirajte samo dostupne sobe za alokaciju
    current_available_rooms_for_allocation = [
        room for room in individual_rooms_data if room.get('is_available', True)
    ]

    # UKUPAN KAPACITET RASPOLOŽIVIH KREVETA (relevantno samo za statistiku)
    total_available_beds_capacity = sum(
        room['single_beds'] * 1 + room['double_beds'] * 2 + room['sofa_beds'] * 2
        for room in current_available_rooms_for_allocation
    )

    if not current_available_rooms_for_allocation:
        return [], 0.0, 0.0, 0, total_guests, "no_rooms_available", 0.0, 0, 0, 0, 0, 0, 0, 0, 0.0, 0.0

    # Pripremamo podatke o sobama
    processed_rooms_for_allocation = []
    num_rooms_within_budget = 0
    for r in current_available_rooms_for_allocation:
        temp_room_data = r.copy()
        max_room_capacity_pairs = r['single_beds'] * 1 + r['double_beds'] * 2 + r['sofa_beds'] * 2

        if max_room_capacity_pairs == 0:
            price_per_guest_room_only_max = float('inf')
        else:
            price_per_guest_room_only_max = r['price'] / max_room_capacity_pairs

        temp_room_data['total_price_per_guest_max_cap'] = price_per_guest_room_only_max + meal_cost_per_guest_for_all_rooms
        temp_room_data['over_max_budget'] = temp_room_data['total_price_per_guest_max_cap'] > max_price_per_guest

        if not temp_room_data['over_max_budget']:
            num_rooms_within_budget += 1

        temp_room_data['calculated_max_capacity_pairs'] = max_room_capacity_pairs
        processed_rooms_for_allocation.append(temp_room_data)

    # Kreiramo listu "bed slots" za alokaciju
    bed_slots_for_allocation = []
    for room_data in processed_rooms_for_allocation:
        bed_slots_for_allocation.append({
            'room_id': room_data['id'],
            'room_name': room_data['name'],
            'priority': room_data['priority'],
            'price': room_data['price'],
            'single_beds_available': room_data['single_beds'],
            'double_beds_available': room_data['double_beds'],
            'sofa_beds_available': room_data['sofa_beds'],
            'accommodated_guests': 0,
            'room_income_this_instance': 0.0,
            'meal_income_this_instance': 0.0,
            'over_max_budget': room_data['over_max_budget'],
            'total_price_per_guest_for_room': room_data['total_price_per_guest_max_cap'],
            'calculated_max_capacity_pairs': room_data['calculated_max_capacity_pairs']
        })

    # Sortiramo "bed slots" za prvu fazu (popunjavanje parova)
    # Prioritet: niži broj prioriteta, zatim dvokrevetni, pa kauči, pa pojedinačni kreveti (svi opadajuće)
    bed_slots_for_allocation.sort(key=lambda x: (
        x['priority'],
        -x['double_beds_available'],
        -x['sofa_beds_available'],
        -x['single_beds_available']
    ))

    # --- Faza 1: Popunjavanje gostiju koji dele krevet (parovi) ---
    if guests_willing_to_share > 0:
        for room_instance in bed_slots_for_allocation:
            if remaining_guests <= 0 or remaining_guests_willing_to_share <= 1:
                break

            # Prvo popunjavamo dvokrevetne krevete
            pairs_in_double_beds = min(room_instance['double_beds_available'], remaining_guests_willing_to_share // 2)
            if pairs_in_double_beds > 0:
                guests_to_add = pairs_in_double_beds * 2
                room_instance['accommodated_guests'] += guests_to_add
                remaining_guests -= guests_to_add
                remaining_guests_willing_to_share -= guests_to_add
                room_instance['double_beds_available'] -= pairs_in_double_beds

            if remaining_guests_willing_to_share >= 2: # Provera je i dalje relevantna ovde
                # Zatim popunjavamo kauče za razvlačenje
                pairs_in_sofa_beds = min(room_instance['sofa_beds_available'], remaining_guests_willing_to_share // 2)
                if pairs_in_sofa_beds > 0:
                    guests_to_add = pairs_in_sofa_beds * 2
                    room_instance['accommodated_guests'] += guests_to_add
                    remaining_guests -= guests_to_add
                    remaining_guests_willing_to_share -= guests_to_add
                    room_instance['sofa_beds_available'] -= pairs_in_sofa_beds


    # --- Faza 2: Popunjavanje preostalih gostiju (pojedinci) ---
    # Sada menjamo strategiju sortiranja za pojedinačne goste.
    # Prioritet:
    # 1. Popuni sobe koje su već delimično zauzete (da se minimizira broj korišćenih soba)
    # 2. Unutar toga, sobe sa višim prioritetom (niža vrednost 'priority')
    # 3. Zatim, sobe sa najmanjim slobodnim kapacitetom (optimalno popunjavanje, da se ne troše veliki kreveti za jednog gosta ako ima manjih opcija)
    # 4. Na kraju, po tipu kreveta: single, double, sofa (da se prvo popune single, pa double, pa sofa ako je potrebno)
    bed_slots_for_allocation.sort(key=lambda x: (
        0 if x['accommodated_guests'] > 0 else 1, # Prvo sobe sa već smeštenim gostima
        x['priority'],                                # Zatim prioritet sobe
        x['single_beds_available'] * 1 + x['double_beds_available'] * 1 + x['sofa_beds_available'] * 1 # Najmanji slobodni kapacitet
    ))


    for room_instance in bed_slots_for_allocation:
        if remaining_guests <= 0:
            break

        # Pokušaj popunjavanja pojedinačnih kreveta
        guests_to_add = min(remaining_guests, room_instance['single_beds_available'])
        if guests_to_add > 0:
            room_instance['accommodated_guests'] += guests_to_add
            remaining_guests -= guests_to_add
            room_instance['single_beds_available'] -= guests_to_add

        if remaining_guests <= 0: # Proveri da li su svi gosti smešteni
            break

        # Ako ima još gostiju i preostalih mesta, popuni dvokrevetne krevete pojedincima
        # Sada dvokrevetni krevet tretiraš kao jedno mesto ako je slobodan
        guests_to_add = min(remaining_guests, room_instance['double_beds_available'] * 1) # * 1 jer ga koristimo za jednog gosta
        if guests_to_add > 0:
            room_instance['accommodated_guests'] += guests_to_add
            remaining_guests -= guests_to_add
            room_instance['double_beds_available'] = 0 # Pretpostavljamo da jedan gost zauzima celu dvokrevetnu sobu/krevet ako je to opcija

        if remaining_guests <= 0:
            break

        # Ako ima još gostiju i preostalih mesta, popuni kauče za razvlačenje pojedincima
        guests_to_add = min(remaining_guests, room_instance['sofa_beds_available'] * 1) # * 1 jer ga koristimo za jednog gosta
        if guests_to_add > 0:
            room_instance['accommodated_guests'] += guests_to_add
            remaining_guests -= guests_to_add
            room_instance['sofa_beds_available'] = 0 # Isto, pretpostavljamo da jedan gost zauzima celu sofu

    # --- Agregacija rezultata ---
    aggregated_allocation = []
    for room_instance in bed_slots_for_allocation:
        if room_instance['accommodated_guests'] > 0:
            aggregated_allocation.append({
                'room_id': room_instance['room_id'],
                'room_name': room_instance['room_name'],
                'priority': room_instance['priority'],
                'guests_accommodated': room_instance['accommodated_guests'],
                'room_income': room_instance['price'], # Prihod od sobe se ne menja
                'meal_income': room_instance['accommodated_guests'] * meal_cost_per_guest_for_all_rooms,
                'single_beds_remaining': room_instance['single_beds_available'],
                'double_beds_remaining': room_instance['double_beds_available'],
                'sofa_beds_remaining': room_instance['sofa_beds_available'],
                'room_capacity': room_instance['calculated_max_capacity_pairs'],
                'total_price_per_guest_for_room': room_instance['total_price_per_guest_for_room'],
                'over_max_budget': room_instance['over_max_budget']
            })
            total_rooms_used_count += 1

    allocation = aggregated_allocation
    allocation.sort(key=lambda x: (x['priority'], x['room_id']))

    total_accommodated_guests = sum(item['guests_accommodated'] for item in allocation)
    total_income_from_rooms = sum(item['room_income'] for item in allocation)
    total_income_from_meals = sum(item['meal_income'] for item in allocation)

    total_room_income_for_num_days = total_income_from_rooms * num_days
    total_meal_income_for_num_days = total_income_from_meals * num_days

    avg_achieved_price_per_bed_room_only = 0.0
    if total_accommodated_guests > 0:
        avg_achieved_price_per_bed_room_only = total_income_from_rooms / total_accommodated_guests

    total_hotel_capacity_beds = sum(room['single_beds'] * 1 + room['double_beds'] * 2 + room['sofa_beds'] * 2 for room in individual_rooms_data)
    total_physical_rooms_in_hotel = len(individual_rooms_data)

    avg_price_per_guest_incl_meals = 0.0
    if total_accommodated_guests > 0:
        avg_price_per_guest_incl_meals = (total_income_from_rooms + total_income_from_meals) / total_accommodated_guests

    avg_price_per_occupied_room = 0.0
    if total_rooms_used_count > 0:
        avg_price_per_occupied_room = total_income_from_rooms / total_rooms_used_count

    status_msg = "success" if remaining_guests == 0 else "partial_success"
    num_available_rooms_total = len(current_available_rooms_for_allocation)

    if num_available_rooms_total == 0:
        status_msg = "no_rooms_available"
    elif num_rooms_within_budget == 0 and total_accommodated_guests > 0:
        status_msg = "all_rooms_over_budget"
    elif num_rooms_within_budget == 0 and total_accommodated_guests == 0 and num_available_rooms_total > 0:
        status_msg = "no_rooms_within_budget_and_no_guests"
    elif remaining_guests > 0 and total_accommodated_guests == 0:
        status_msg = "no_guests_accommodated"

    return allocation, total_income_from_rooms, total_income_from_meals, total_accommodated_guests, remaining_guests, status_msg, avg_achieved_price_per_bed_room_only, total_rooms_used_count, num_rooms_within_budget, total_hotel_capacity_beds, avg_price_per_guest_incl_meals, avg_price_per_occupied_room, total_available_beds_capacity, total_physical_rooms_in_hotel, total_room_income_for_num_days, total_meal_income_for_num_days

# Ostatak koda (main funkcija i UI) ostaje isti kao u originalnom kodu

# --- Glavna aplikacija ---
def main():
    st.set_page_config(layout="wide", page_title="Optimizacija Gostiju po Sobama")
    st.markdown("<h5 style='font-size: 24px; color: #0056b3; text-align: center;'>🏨 Optimizacija Rasporeda Gostiju po Sobama</h1>", unsafe_allow_html=True)
    st.markdown("---")

    if 'individual_rooms' not in st.session_state:
        st.session_state.individual_rooms = []
    if 'global_meal_prices' not in st.session_state:
        st.session_state.global_meal_prices = {'breakfast': 10.0, 'lunch': 15.0, 'dinner': 20.0}

    # Inicijalizacija predefinisanih soba ako ih nema / AKO SE NEKA SOFA NE RAZVLACI ONDA JE TREBA UBACITI KAO JEDAN SINGLE DA NE BI SE RACUNALO X2
    if not st.session_state.individual_rooms and 'predefined_rooms_added_v2' not in st.session_state:
        predefined_individual_rooms = [
            {'id': 'S-001', 'name': 'King | K1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'priority': 1, 'is_available': True},
            {'id': 'S-002', 'name': 'Exec | K1+T2+S1', 'single_beds': 2, 'double_beds': 1, 'sofa_beds': 1, 'price': 200.0, 'priority': 4, 'is_available': True},
            {'id': 'S-003', 'name': 'King | K1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'priority': 1, 'is_available': True},
            {'id': 'S-004', 'name': 'Twin | T2', 'single_beds': 2, 'double_beds': 0, 'sofa_beds': 0, 'price': 110.0, 'priority': 2, 'is_available': True},
            {'id': 'S-005', 'name': 'King | K1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'priority': 1, 'is_available': True},
            {'id': 'S-101', 'name': 'Junr | K1+S1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 180.0, 'priority': 3, 'is_available': True},
            {'id': 'S-102', 'name': 'Junr | K1+S1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 180.0, 'priority': 3, 'is_available': True},
            {'id': 'S-103', 'name': 'King | K1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'priority': 1, 'is_available': True},
            {'id': 'S-104', 'name': 'Twin | T2', 'single_beds': 2, 'double_beds': 0, 'sofa_beds': 0, 'price': 110.0, 'priority': 2, 'is_available': True},
            {'id': 'S-105', 'name': 'Twin | T2', 'single_beds': 2, 'double_beds': 0, 'sofa_beds': 0, 'price': 110.0, 'priority': 2, 'is_available': True},
            {'id': 'S-106', 'name': 'Twin | T2', 'single_beds': 2, 'double_beds': 0, 'sofa_beds': 0, 'price': 110.0, 'priority': 2, 'is_available': True},
            {'id': 'S-107', 'name': 'King | K1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'priority': 1, 'is_available': True},
            {'id': 'S-108', 'name': 'King | K1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'priority': 1, 'is_available': True},
            {'id': 'S-109', 'name': 'King | K1+S1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 110.0, 'priority': 1, 'is_available': True},
            {'id': 'S-110', 'name': 'Exec | K1+T1+S1', 'single_beds': 1, 'double_beds': 1, 'sofa_beds': 1, 'price': 200.0, 'priority': 4, 'is_available': True},
            {'id': 'S-111', 'name': 'Junr | K1+S1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 180.0, 'priority': 3, 'is_available': True},
            {'id': 'S-201', 'name': 'Junr | K1+S1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 180.0, 'priority': 3, 'is_available': True},
            {'id': 'S-202', 'name': 'Exec | K1+T2+S1', 'single_beds': 2, 'double_beds': 1, 'sofa_beds': 1, 'price': 200.0, 'priority': 4, 'is_available': True},
            {'id': 'S-203', 'name': 'King | K1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'priority': 1, 'is_available': True},
            {'id': 'S-204', 'name': 'Twin | T2', 'single_beds': 2, 'double_beds': 0, 'sofa_beds': 0, 'price': 110.0, 'priority': 2, 'is_available': True},
            {'id': 'S-205', 'name': 'Twin | T2', 'single_beds': 2, 'double_beds': 0, 'sofa_beds': 0, 'price': 110.0, 'priority': 2, 'is_available': True},
            {'id': 'S-206', 'name': 'Twin | T2', 'single_beds': 2, 'double_beds': 0, 'sofa_beds': 0, 'price': 110.0, 'priority': 2, 'is_available': True},
            {'id': 'S-207', 'name': 'King | K1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'priority': 1, 'is_available': True},
            {'id': 'S-208', 'name': 'King | K1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 0, 'price': 110.0, 'priority': 1, 'is_available': True},
            {'id': 'S-209', 'name': 'King | K1+S1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 110.0, 'priority': 1, 'is_available': True},
            {'id': 'S-210', 'name': 'Exec | K1+T1+S1', 'single_beds': 1, 'double_beds': 1, 'sofa_beds': 1, 'price': 200.0, 'priority': 4, 'is_available': True},
            {'id': 'S-211', 'name': 'Junr | K1+S1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 180.0, 'priority': 3, 'is_available': True},
            {'id': 'S-301', 'name': 'Royl | K1+T2+S1', 'single_beds': 2, 'double_beds': 1, 'sofa_beds': 1, 'price': 240.0, 'priority': 5, 'is_available': True},
            {'id': 'S-302', 'name': 'Royl | K1+S1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 240.0, 'priority': 5, 'is_available': True},
            {'id': 'S-303', 'name': 'Junr | K1+S1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 180.0, 'priority': 3, 'is_available': True},
            {'id': 'S-304', 'name': 'Royl | K1+S1', 'single_beds': 0, 'double_beds': 1, 'sofa_beds': 1, 'price': 240.0, 'priority': 5, 'is_available': True},
            {'id': 'S-305', 'name': 'Royl | K1+T2+S1', 'single_beds': 2, 'double_beds': 1, 'sofa_beds': 1, 'price': 240.0, 'priority': 5, 'is_available': True},
        ]
        st.session_state.individual_rooms.extend(predefined_individual_rooms)
        st.session_state.predefined_rooms_added_v2 = True


    st.sidebar.header("Kontrole i Podešavanja")
    # Premesti dugme "Pokreni Optimizaciju" na sam vrh sidebara
    allocation_button = st.sidebar.button("Pokreni Optimizaciju Rasporeda", type="primary", use_container_width=True, key="run_optimization_button")
    st.sidebar.markdown("---") # Odvajanje nakon glavnog dugmeta

    # Smanjenje vertikalnog razmaka - grupisanjem unutar st.container()
    with st.sidebar.container():
        st.subheader("Parametri Gostiju")
        total_guests = st.number_input(
            "Ukupan broj gostiju za raspored",
            min_value=1,
            value=30,
            step=1,
            help="Unesite ukupan broj gostiju koje treba rasporediti."
        )
        
        guests_willing_to_share = st.number_input(
            "Broj gostiju spremnih da dele bračni/sofa krevet",
            min_value=0,
            value=min(total_guests, 10),
            step=1,
            help="Unesite broj gostiju (parova) koji su spremni da dele bračni ili sofa krevet. Ako je unet neparan broj, biće zaokruženo na najbliži niži paran broj."
        )
        if guests_willing_to_share % 2 != 0:
            guests_willing_to_share = guests_willing_to_share - 1
            st.warning(f"Broj gostiju spremnih da dele krevet mora biti paran. Postavljeno na: {guests_willing_to_share}")
    st.sidebar.markdown("---")

    # Novo polje za broj dana
    with st.sidebar.container():
        st.subheader("Trajanje boravka")
        num_days = st.number_input(
            "Broj dana boravka",
            min_value=1,
            value=st.session_state.get('num_days_stay', 1), # Dodato da se pamti vrednost
            step=1,
            help="Unesite broj dana za koje se vrši raspored i obračun prihoda."
        )
        st.session_state.num_days_stay = num_days # Sačuvaj num_days u session_state
    st.sidebar.markdown("---")


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
    max_price_per_guest = st.sidebar.number_input(
        "Ciljna maksimalna ukupna cena po gostu (smeštaj + obroci, €)",
        min_value=0.0,
        value=st.session_state.get('max_price_per_guest', 80.0),
        step=5.0,
        help="Ovo je ciljna cena po gostu. Aplikacija će rasporediti goste bez obzira na ovu cenu, ali će naznačiti sobe koje prelaze ovaj budžet."
    )
    st.session_state.max_price_per_guest = max_price_per_guest
    st.sidebar.markdown("---")

    # Reset dugme na dnu sidebara
    if st.sidebar.button("Resetuj sve postavke", key="reset_button"):
        st.session_state.clear()
        st.rerun()

    # --- Glavni tabovi: Upravljanje Hotelom i Izveštaji i Optimizacija ---
    tab_hotel_management, tab_reports = st.tabs(["⚙️ Upravljanje Hotelom", "📊 Izveštaji i Optimizacija"])

    with tab_hotel_management:
        st.markdown("## ⚙️ Upravljanje Hotelom")
        st.write("Ovde možete konfigurisati pojedinačne sobe i cene obroka.")

        # --- Pod-tabovi unutar "Upravljanje Hotelom" ---
        tab_available_rooms, tab_edit_rooms_and_availability, tab_meal_settings = st.tabs([ 
            "🔢 Pregled Soba", 
            "✏️ Izmeni Sobe i Dostupnost", 
            "🍽️ Postavke Cena Obroka"
        ])

        with tab_available_rooms:
            st.markdown("### 🔢 Pregled svih Soba")
            st.write("Tabelarni prikaz svih soba i njihovih atributa.")

            if not st.session_state.individual_rooms:
                st.info("Nema definisanih soba. Sobe su predefinisane u kodu.")
            else:
                rooms_for_display = []
                for room in st.session_state.individual_rooms:
                    room_max_cap = room['single_beds'] * 1 + room['double_beds'] * 2 + room['sofa_beds'] * 2
                    rooms_for_display.append({
                        "ID Sobe": room['id'],
                        "Naziv Sobe": room['name'],
                        "TWIN Kreveti": room['single_beds'],
                        "KING Kreveti": room['double_beds'],
                        "SOFA Kreveti": room['sofa_beds'],
                        "Maks. Kapacitet": room_max_cap,
                        "Cena (€)": f"{room['price']:.2f}",
                        "Prioritet": room['priority'],
                        "Dostupnost": "Da" if room.get('is_available', True) else "Ne"
                    })
                    
                df_rooms = pd.DataFrame(rooms_for_display)
                st.dataframe(df_rooms, use_container_width=True, hide_index=True)


        with tab_edit_rooms_and_availability: 
            st.markdown("### ✏️ Izmeni Sobe i Dostupnost")
            st.write("Kliknite na sobu ispod da biste izmenili njene detalje, uključujući dostupnost.")

            if not st.session_state.individual_rooms:
                st.info("Trenutno nema dodanih soba za izmenu.")
            else:
                for i, room in enumerate(st.session_state.individual_rooms[:]):
                    room_max_cap = room['single_beds'] * 1 + room['double_beds'] * 2 + room['sofa_beds'] * 2
                    expander_title = f"⚙️ {room['name']} (ID: {room['id']}, Kapacitet: {room_max_cap}, Cena: {room['price']}€, Prioritet: {room['priority']})"
                    with st.expander(expander_title):
                        with st.form(f"edit_room_form_{room['id']}"):
                            col_id, col_name = st.columns(2)
                            with col_id:
                                st.text_input("ID Sobe (ne može se menjati)", value=room['id'], disabled=True, key=f"edit_id_disabled_{room['id']}")
                            with col_name:
                                new_name = st.text_input("Naziv Sobe", value=room['name'], key=f"edit_name_{room['id']}")
                            
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                new_single_beds = st.number_input("Broj singl kreveta", value=room['single_beds'], min_value=0, step=1, key=f"edit_single_beds_{room['id']}")
                            with col2:
                                new_double_beds = st.number_input("Broj bračnih kreveta", value=room['double_beds'], min_value=0, step=1, key=f"edit_double_beds_{room['id']}")
                            with col3:
                                new_sofa_beds = st.number_input("Broj sofa na razvlačenje", value=room['sofa_beds'], min_value=0, step=1, key=f"edit_sofa_beds_{room['id']}")

                            col4, col5, col6 = st.columns(3) 
                            with col4:
                                new_price = st.number_input("Cena po noćenju", value=room['price'], min_value=0.0, step=10.0, key=f"edit_price_{room['id']}", format="%.2f")
                            with col5:
                                new_priority = st.number_input("Prioritet", value=room.get('priority', 3), min_value=1, step=1, key=f"edit_priority_{room['id']}")
                            with col6: 
                                new_availability = st.checkbox("Dostupna za izdavanje", value=room.get('is_available', True), key=f"edit_availability_{room['id']}")


                            st.info(f"Cene obroka za ovu sobu koriste globalne postavke: Doručak {st.session_state.global_meal_prices['breakfast']:.2f}€, Ručak {st.session_state.global_meal_prices['lunch']:.2f}€, Večera {st.session_state.global_meal_prices['dinner']:.2f}€.")

                            update_submitted = st.form_submit_button("Ažuriraj sobu", type="primary")
                            if update_submitted:
                                if (new_single_beds + new_double_beds + new_sofa_beds) == 0:
                                    st.error("Soba mora imati barem jedan krevet (singl, bračni ili sofu).")
                                else:
                                    original_room_index = next((idx for idx, r_item in enumerate(st.session_state.individual_rooms) if r_item['id'] == room['id']), -1)
                                    if original_room_index != -1:
                                        st.session_state.individual_rooms[original_room_index].update({
                                            'name': new_name,
                                            'single_beds': int(new_single_beds),
                                            'double_beds': int(new_double_beds),
                                            'sofa_beds': int(new_sofa_beds),
                                            'price': float(new_price),
                                            'priority': int(new_priority),
                                            'is_available': new_availability 
                                        })
                                        st.success(f"Soba **{new_name} (ID: {room['id']})** ažurirana.")
                                        st.rerun()
                                    else:
                                        st.error("Greška pri ažuriranju sobe: Soba nije pronađena.")


        with tab_meal_settings:
            st.markdown("### 🍽️ Postavke Cena Obroka (Globalne)")
            st.write("Ovde možete podesiti globalne cene za doručak, ručak i večeru. Ove cene se primenjuju na sve goste.")

            with st.form("global_meal_prices_form"):
                new_bf_price = st.number_input("Cena doručka (€)", min_value=0.0, step=1.0,
                                                value=st.session_state.global_meal_prices.get('breakfast', 0.0), key="global_bf_price", format="%.2f")
                new_lunch_price = st.number_input("Cena ručka (€)", min_value=0.0, step=1.0,
                                                    value=st.session_state.global_meal_prices.get('lunch', 0.0), key="global_lunch_price", format="%.2f")
                new_dinner_price = st.number_input("Cena večere (€)", min_value=0.0, step=1.0,
                                                    value=st.session_state.global_meal_prices.get('dinner', 0.0), key="global_dinner_price", format="%.2f")
                
                meal_price_submitted = st.form_submit_button("Sačuvaj cene obroka", type="primary")
                if meal_price_submitted:
                    st.session_state.global_meal_prices['breakfast'] = new_bf_price
                    st.session_state.global_meal_prices['lunch'] = new_lunch_price
                    st.session_state.global_meal_prices['dinner'] = new_dinner_price
                    st.success("Cene obroka su uspešno ažurirane!")
                    st.rerun()

    with tab_reports:
        st.markdown("## 📊 Izveštaji i Optimizacija")
        st.write("Rezultati rasporeda gostiju po sobama i finansijski pregled.")

        if allocation_button:
            if not st.session_state.individual_rooms:
                st.error("Nema definisanih soba. Molimo omogućite sobe ili ih dodajte u kodu.")
            else:
                st.info("Pokrećem optimizaciju rasporeda...")
                allocation_results, total_room_income, total_income_from_meals, total_accommodated, remaining_guests_after_allocation, status_message, avg_achieved_price_per_bed, total_rooms_used_count, num_rooms_within_budget, total_hotel_capacity_beds, avg_price_per_guest_incl_meals, avg_price_per_occupied_room, total_available_beds_capacity, total_physical_rooms_in_hotel, total_room_income_for_num_days, total_meal_income_for_num_days = perform_allocation(
                    total_guests, guests_willing_to_share, max_price_per_guest, breakfast_chosen, lunch_chosen, dinner_chosen,
                    st.session_state.individual_rooms, st.session_state.global_meal_prices, num_days # Dodat num_days
                )

                st.session_state.last_total_guests = total_guests 
                st.session_state.last_allocation_results = allocation_results
                st.session_state.last_total_room_income = total_room_income
                st.session_state.last_total_meal_income = total_income_from_meals 
                st.session_state.last_total_accommodated = total_accommodated
                st.session_state.last_remaining_guests = remaining_guests_after_allocation
                st.session_state.last_status_message = status_message
                st.session_state.last_avg_achieved_price_per_bed = avg_achieved_price_per_bed
                st.session_state.last_total_rooms_used_count = total_rooms_used_count
                st.session_state.last_num_rooms_within_budget = num_rooms_within_budget
                st.session_state.last_total_hotel_capacity_beds = total_hotel_capacity_beds
                st.session_state.last_avg_price_per_guest_incl_meals = avg_price_per_guest_incl_meals
                st.session_state.last_avg_price_per_occupied_room = avg_price_per_occupied_room
                st.session_state.last_total_available_beds_capacity = total_available_beds_capacity
                st.session_state.last_total_physical_rooms_in_hotel = total_physical_rooms_in_hotel
                st.session_state.last_total_room_income_for_num_days = total_room_income_for_num_days # Sačuvaj novi prihod
                st.session_state.last_total_meal_income_for_num_days = total_meal_income_for_num_days # Sačuvaj novi prihod
                st.rerun()

        # Prikaz rezultata poslednje alokacije (iz session_state-a)
        if 'last_allocation_results' in st.session_state and st.session_state.last_allocation_results:
            st.markdown("---")
            st.markdown("### Detaljan Izveštaj Rasporeda")

            # Poruke o statusu
            if st.session_state.last_status_message == "no_rooms_available":
                st.warning("Nema dostupnih soba za alokaciju. Molimo omogućite neke sobe u sekciji 'Upravljanje Hotelom' -> 'Izmeni Sobe i Dostupnost'.")
            elif st.session_state.last_status_message == "all_rooms_over_budget":
                st.warning(f"Svi gosti su smešteni, ali nijedna soba nije ispunila ciljnu cenu od {st.session_state.max_price_per_guest:.2f}€ po gostu (smeštaj + obroci).")
            elif st.session_state.last_status_message == "no_rooms_within_budget_and_no_guests":
                st.warning(f"Nema soba koje ispunjavaju ciljnu cenu od {st.session_state.max_price_per_guest:.2f}€ po gostu, i nijedan gost nije smešten. Pokušajte da povećate budžet ili smanjite cene soba.")
            elif st.session_state.last_remaining_guests > 0:
                if st.session_state.last_total_accommodated > 0:
                    st.warning(f"Uspeli smo da smestimo {st.session_state.last_total_accommodated} od {st.session_state.last_total_guests} gostiju. Ostalo je {st.session_state.last_remaining_guests} gostiju bez smeštaja.")
                else:
                    st.error(f"Nijedan gost nije smešten. Proverite raspoloživost soba, kapacitete i budžet.")
            else:
                st.success(f"Uspešno je smešteno svih {st.session_state.last_total_guests} gostiju!")

            # Sumarni pregled ključnih metrika - KAO TABELA
            st.markdown("### Sumarni pregled ključnih metrika:")

            # **Dodato: Preuzimanje num_days iz session_state-a**
            # Ovo je važno jer se num_days postavlja u sidebaru i mora biti dostupan ovde.
            try:
                num_days_display = st.session_state.get('num_days_stay', 1)
            except AttributeError:
                num_days_display = 1
                st.warning("Varijabla 'num_days_stay' nije pronađena u session_state. Postavljena je na podrazumevanu vrednost 1.")

            summary_data = [
                {"Metrika": "Ukupan Broj Gostiju (za raspored)", "Vrednost": st.session_state.last_total_guests},
                {"Metrika": "Broj dana boravka", "Vrednost": num_days_display}, # Korišćenje num_days_display
                {"Metrika": "Ukupan Prihod (Sobe, po danu)", "Vrednost": f"{st.session_state.last_total_room_income:,.2f} €"},
                {"Metrika": "Ukupan Prihod (Obroci, po danu)", "Vrednost": f"{st.session_state.last_total_meal_income:,.2f} €"},
                {"Metrika": f"Ukupan Prihod (Sobe, za {num_days_display} dana)", "Vrednost": f"{st.session_state.last_total_room_income_for_num_days:,.2f} €"},
                {"Metrika": f"Ukupan Prihod (Obroci, za {num_days_display} dana)", "Vrednost": f"{st.session_state.last_total_meal_income_for_num_days:,.2f} €"},
                {"Metrika": f"Ukupan Prihod Hotela (za {num_days_display} dana)", "Vrednost": f"{(st.session_state.last_total_room_income_for_num_days + st.session_state.last_total_meal_income_for_num_days):,.2f} €"}, # Dodat Ukupan Prihod Hotela
                {"Metrika": "Ukupno Smešteno Gostiju", "Vrednost": st.session_state.last_total_accommodated},
                {"Metrika": "Preostalo Gostiju bez smeštaja", "Vrednost": st.session_state.last_remaining_guests},
                {"Metrika": "Korišćeno Soba", "Vrednost": st.session_state.last_total_rooms_used_count},
                
                {"Metrika": "Prosečna ostvarena cena po gostu (samo smeštaj)", "Vrednost": f"{st.session_state.last_avg_achieved_price_per_bed:,.2f} €"},
                {"Metrika": "Prosečna cena po gostu (smeštaj + obroci)", "Vrednost": f"{st.session_state.last_avg_price_per_guest_incl_meals:,.2f} €"},
                {"Metrika": "Prosečna cena po zauzetoj sobi", "Vrednost": f"{st.session_state.last_avg_price_per_occupied_room:,.2f} €"},
                {"Metrika": "Ukupan kapacitet hotela (ležajeva)", "Vrednost": st.session_state.last_total_hotel_capacity_beds},
                {"Metrika": "Ukupan kapacitet dostupnih soba (ležajeva)", "Vrednost": st.session_state.last_total_available_beds_capacity},
                
                
            ]
            df_summary = pd.DataFrame(summary_data)

            # Primena stilizovanja na sumarnu tabelu
            styled_summary_df = df_summary.style.apply(lambda row: style_summary_table(row, num_days_display), axis=1)
            st.dataframe(styled_summary_df, use_container_width=True, hide_index=True, height=565) # Fiksna visina za bolji prikaz

            st.markdown("---")

            # Prikaz alokacije po sobama
            st.markdown("### Raspored Gostiju po Sobama")
            if st.session_state.last_allocation_results:
                allocation_display_data = []
                for item in st.session_state.last_allocation_results:
                    # Izračunaj ukupan prihod po sobi
                    total_room_revenue = item['room_income'] + item['meal_income']
                    # Proveri da li je soba preko budžeta za prikaz
                    over_budget_status = "DA" if item['over_max_budget'] else "NE"

                    allocation_display_data.append({
                        "ID Sobe": item['room_id'],
                        "Naziv Sobe": item['room_name'],
                       
                        "Smešteno Gostiju": item['guests_accommodated'], # Vraćen naziv
                        "Prihod od Sobe (po danu)": f"{item['room_income']:.2f} €", # Vraćen naziv
                        "Prihod od Obroka (po danu)": f"{item['meal_income']:.2f} €", # Vraćen naziv
                        "Tot.Prihod po Sobi (po danu)": f"{total_room_revenue:.2f} €",
                        "Tot.Prihod po Sobi (za period)": f"{(total_room_revenue * num_days_display):.2f} €", # Dodatni KPI
                        "Soba iznad budžeta (po gostu)": over_budget_status, # Vraćen naziv
                        "Cena po gostu (smeštaj + obroci)": f"{item['total_price_per_guest_for_room']:.2f} €" # Vraćen naziv
                        # Dodatni kreveti koji su bili u drugom kodu (single_beds_remaining, double_beds_remaining, sofa_beds_remaining)
                        # Ako želite da ih vratite, dodajte ih ovde u dictionary i u display_cols_allocation listu ispod.
                    })
                
                allocation_df = pd.DataFrame(allocation_display_data)

                # Konvertovanje numeričkih kolona u float pre stilizovanja
                # Ovo je i dalje potrebno ako su vrednosti u DataFrame-u stringovi sa '€' i zarezima
                for col in ["Prihod od Sobe (po danu)", "Prihod od Obroka (po danu)", "Cena po gostu (smeštaj + obroci)"]:
                    # Provera da li je kolona već numerička da bi se izbegla greška ako je već konvertovana
                    if not pd.api.types.is_numeric_dtype(allocation_df[col]):
                        # Uklanjanje "€" i zarez pre konverzije
                        allocation_df[col] = allocation_df[col].str.replace(' €', '').str.replace(',', '').astype(float)


                # Redosled kolona za prikaz (prilagođeno na originalne KPI-jeve)
                display_cols_allocation = [
                    "ID Sobe",
                    "Naziv Sobe",
                   
                    "Smešteno Gostiju",
                    "Prihod od Sobe (po danu)",
                    "Prihod od Obroka (po danu)",
                    "Tot.Prihod po Sobi (po danu)",
                    "Tot.Prihod po Sobi (za period)", # Korišćenje num_days_display
                    "Soba iznad budžeta (po gostu)",
                    "Cena po gostu (smeštaj + obroci)"
                ]
                
                df_to_style_allocation = allocation_df[display_cols_allocation]
                styled_allocation_df = df_to_style_allocation.style.apply(highlight_over_budget, axis=1)

                # Formatiranje numeričkih kolona za prikaz nakon stilizovanja
                styled_allocation_df = styled_allocation_df.format({
                    'Prihod od Sobe (po danu)': '{:,.2f} €',
                    'Prihod od Obroka (po danu)': '{:,.2f} €',
                    'Cena po gostu (smeštaj + obroci)': '{:,.2f} €',
                })

                st.dataframe(styled_allocation_df, use_container_width=True, hide_index=True, height=600)
            else:
                st.info("Nema generisanog rasporeda.")

if __name__ == "__main__":
    main()