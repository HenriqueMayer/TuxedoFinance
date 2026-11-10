from config.testing import ApiTestCase
from ledger.categories import Category

EXPORT = "/api/ledger/categories/export"
IMPORT = "/api/ledger/categories/import"
HEADER = "name,transaction_type,parent_category"


class CategoryTransferTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        Category.objects.filter(user=self.user).delete()  # The defaults of a new owner.
        self.health = Category.objects.create(
            user=self.user, name="Saúde", transaction_type="EXPENSE"
        )
        Category.objects.create(user=self.user, name="Farmácia", parent_category=self.health)
        Category.objects.create(user=self.user, name="Salário", transaction_type="INCOME")

    def export(self):
        response = self.get(EXPORT)
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def load(self, text):
        return self.post(IMPORT, {"content": text})

    def test_the_export_is_a_csv_file_with_every_category(self):
        response = self.export()
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn('filename="tuxedo-categories.csv"', response["Content-Disposition"])
        self.assertEqual(
            response.content.decode("utf-8-sig").splitlines(),
            [HEADER, "Farmácia,,Saúde", "Salário,INCOME,", "Saúde,EXPENSE,"],
        )

    def test_an_import_creates_the_new_categories_with_their_parents(self):
        text = f"{HEADER}\nTransporte,EXPENSE,\nEstacionamento,,Transporte\nSaúde,EXPENSE,\n"
        response = self.load(text)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json(), {"created": 2, "existing": 1})
        parking = Category.objects.get(user=self.user, name="Estacionamento")
        self.assertEqual(parking.parent_category.name, "Transporte")
        self.assertEqual(Category.objects.filter(user=self.user).count(), 5)

    def test_the_export_of_one_owner_is_the_import_of_another(self):
        text = self.export().content.decode("utf-8-sig")
        self.client.force_login(self.other)
        Category.objects.filter(user=self.other).delete()
        self.assertEqual(self.load(text).json(), {"created": 3, "existing": 0})
        self.assertEqual(self.export().content.decode("utf-8-sig"), text)
        self.assertEqual(Category.objects.filter(user=self.user).count(), 3)

    def test_a_wrong_file_changes_nothing(self):
        wrong = (
            "nome,tipo\nSaúde,EXPENSE\n",
            f"{HEADER}\nA,WRONG,\n",
            f"{HEADER}\nFilha,,Mãe que não existe\n",
            f"{HEADER}\nA,,B\nB,,A\n",
            "",
        )
        for text in wrong:
            with self.subTest(text=text):
                self.assert_errors(self.load(text), 400, "content")
        self.assertEqual(Category.objects.filter(user=self.user).count(), 3)

    def test_the_export_holds_the_categories_of_the_owner_only(self):
        Category.objects.create(user=self.other, name="Alheia")
        self.assertNotIn("Alheia", self.export().content.decode())


class SessionTests(ApiTestCase):
    signed_in = False

    def test_the_transfer_needs_a_session(self):
        self.assertEqual(self.get(EXPORT).status_code, 401)
        self.assertEqual(self.post(IMPORT, {"content": HEADER}).status_code, 401)
