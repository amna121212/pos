"""Idempotent student-curated *fictional* Lahore master-data seed (no invented sales)."""
from decimal import Decimal
import os
from werkzeug.security import generate_password_hash
from sqlalchemy import select, func
from app import create_app, db
from app.models import (Business, Branch, User, BusinessUser, Category, Product,
    BranchProduct, DiningTable, PaymentMethod, Supplier, Printer, CashRegister)
from app.seeddata.naming import OWNER_NAMES, PRIMARY_SUPPLIER

# Deliberately fictional names; menu and prices are illustrative PKR data.
DATA = [
    dict(name='Lahore Grill House', slug='lahore-grill-house', kind='restaurant',
         branches=[('JT','Johar Town','Johar Town'),('DHA','DHA Phase 5','DHA Phase 5')],
         menu={'BBQ':[('Chicken Tikka',650,360),('Seekh Kebab',480,250),('Malai Boti',890,510),('Chicken Karahi Half',1450,850)],
               'Rice':[('Chicken Biryani',420,220),('Chicken Pulao',390,200)],
               'Drinks':[('Mint Margarita',350,125),('Lemon Soda',240,80)]}),
    dict(name='Urban Bites Lahore', slug='urban-bites-lahore', kind='restaurant',
         branches=[('GUL','Gulberg III','Gulberg III'),('MT','Model Town','Model Town')],
         menu={'Burgers':[('Classic Beef Burger',890,470),('Zinger Burger',640,320),('Double Cheese Burger',1190,670)],
               'Sides':[('Loaded Fries',520,260),('Chicken Nuggets',470,220)],
               'Drinks':[('Cold Coffee',450,180),('Peach Iced Tea',390,140),('Mineral Water',120,45)]}),
    dict(name='Daily Mart Lahore', slug='daily-mart-lahore', kind='retail',
         branches=[('WT','Wapda Town','Wapda Town'),('FT','Faisal Town','Faisal Town')],
         menu={'Dairy':[('Milk 1L',350,310),('Yogurt 500g',220,175),('Butter 200g',590,515)],
               'Bakery':[('Bread Large',240,195),('Burger Buns 6 Pack',270,225)],
               'Beverages':[('Juice 1L',410,340),('Bottled Water 1.5L',150,110)],
               'Pantry':[('Basmati Rice 1kg',460,395),('Sugar 1kg',190,160)]}),
]


def get_or_create(model, lookups, **defaults):
    found = db.session.execute(select(model).filter_by(**lookups)).scalar_one_or_none()
    if found:
        return found
    record = model(**lookups, **defaults)
    db.session.add(record)
    db.session.flush()
    return record


def main():
    app = create_app()
    with app.app_context():
        db_name = db.session.execute(select(func.current_database())).scalar_one()
        if db_name != 'retail_pos_db':
            raise RuntimeError('Refusing to seed unexpected database: ' + db_name)
        # Transaction is committed only after every record succeeds.
        try:
            for item in DATA:
                business = get_or_create(Business, {'slug': item['slug']},
                    name=item['name'], business_type=item['kind'], city='Lahore', is_demo=True)
                for role, label in [('cash','Cash'),('card','Card'),('bank_transfer','Bank Transfer')]:
                    get_or_create(PaymentMethod, {'business_id':business.id,'code':role}, label=label)
                get_or_create(Supplier, {'business_id':business.id,'name':PRIMARY_SUPPLIER},city='Lahore')
                owner_email = f"demo-owner-{business.slug}@example.invalid"
                owner = get_or_create(User, {'email':owner_email},
                    display_name=OWNER_NAMES.get(item["slug"], business.name + " Owner"),
                    password_hash=generate_password_hash(os.urandom(24).hex()))
                # owner is a business-wide membership (branch_id=None)
                get_or_create(BusinessUser, {'business_id':business.id,'user_id':owner.id,'role':'owner'})
                branches=[]
                for code, name, area in item['branches']:
                    branch=get_or_create(Branch,{'business_id':business.id,'code':code},name=name,area=area,city='Lahore')
                    branches.append(branch)
                    get_or_create(Printer,{'branch_id':branch.id,'label':'Receipt printer'},purpose='receipt',connection_type='browser')
                    get_or_create(CashRegister,{'branch_id':branch.id,'code':'COUNTER-01'},label='Main Counter')
                    if item['kind']=='restaurant':
                        get_or_create(Printer,{'branch_id':branch.id,'label':'Kitchen printer'},purpose='kitchen',connection_type='browser')
                        for n in range(1,7):
                            get_or_create(DiningTable,{'branch_id':branch.id,'table_number':f'T{n:02d}'},capacity=4)
                for category_name, products in item['menu'].items():
                    category=get_or_create(Category,{'business_id':business.id,'name':category_name})
                    for j,(name,price,cost) in enumerate(products,1):
                        sku=(category_name[:3].upper().replace(' ','')+'-'+str(j).zfill(3))
                        product=get_or_create(Product,{'business_id':business.id,'sku':sku},
                            category_id=category.id,name=name,
                            kind='menu_item' if item['kind']=='restaurant' else 'retail_item',
                            base_cost=Decimal(cost))
                        for idx,branch in enumerate(branches):
                            # Branch prices can legitimately differ.
                            get_or_create(BranchProduct,{'branch_id':branch.id,'product_id':product.id},
                                business_id=business.id,sale_price=Decimal(price+idx*20))
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        for model in [Business,Branch,User,BusinessUser,Category,Product,BranchProduct,
                      DiningTable,PaymentMethod,Supplier,Printer,CashRegister]:
            print(f'{model.__tablename__:20} {db.session.query(model).count():5}')
        print('SUCCESS: POS foundation seeded (no sales history yet).')

if __name__=='__main__':
    main()
